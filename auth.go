package main

import (
	"context"
	"net/http"
	"os"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

// Ключи для контекста (кастомный тип предотвращает ошибки и коллизии)
type contextKey string

const (
	ContextUserID      contextKey = "user_id"
	ContextRole        contextKey = "role"
	ContextPermissions contextKey = "permissions"
	ContextCourseID    contextKey = "course_id"
)

// MyCustomClaims структура токена согласно вашему ТЗ
type MyCustomClaims struct {
	UserID      int      `json:"user_id"`
	Role        string   `json:"role"`
	Permissions []string `json:"permissions"`
	IsBlocked   bool     `json:"is_blocked"`
	CourseID    int      `json:"course_id"`
	jwt.RegisteredClaims
}

// AuthMiddleware — единый Middleware для проверки авторизации и прав
func AuthMiddleware(requiredPermission string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "Missing token", http.StatusUnauthorized)
			return
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		// Секрет берется из переменной окружения, как в вашем auth.go
		secret := []byte(os.Getenv("JWT_SECRET"))
		if len(secret) == 0 {
			secret = []byte("iplaygodotandclaimfun") // Default из main.go
		}

		claims := &MyCustomClaims{}
		token, err := jwt.ParseWithClaims(tokenString, claims, func(token *jwt.Token) (interface{}, error) {
			return secret, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		// ТЗ: Если пользователь заблокирован — отвечаем 418
		if claims.IsBlocked {
			w.WriteHeader(http.StatusTeapot)
			w.Write([]byte("I'm a teapot (User is blocked)"))
			return
		}

		// Проверка прав (Permissions)
		if requiredPermission != "" {
			hasPerm := false
			for _, p := range claims.Permissions {
				if p == requiredPermission {
					hasPerm = true
					break
				}
			}
			if !hasPerm {
				http.Error(w, "Forbidden: missing permission "+requiredPermission, http.StatusForbidden)
				return
			}
		}

		// Записываем данные в контекст, используя типизированные ключи
		ctx := r.Context()
		ctx = context.WithValue(ctx, ContextUserID, claims.UserID)
		ctx = context.WithValue(ctx, ContextRole, claims.Role)
		ctx = context.WithValue(ctx, ContextPermissions, claims.Permissions)
		ctx = context.WithValue(ctx, ContextCourseID, claims.CourseID)

		next.ServeHTTP(w, r.WithContext(ctx))
	}
}
