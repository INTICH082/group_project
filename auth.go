package main

import (
	"context"
	"net/http"
	"os"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

// Ключи для контекста (лучше использовать кастомный тип, чтобы избежать коллизий)
type contextKey string

const (
	ContextUserID      contextKey = "user_id"
	ContextRole        contextKey = "role"
	ContextPermissions contextKey = "permissions"
	ContextCourseID    contextKey = "course_id"
)

// CheckAuth проверяет токен и извлекает данные в контекст
func CheckAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "Missing token", http.StatusUnauthorized)
			return
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		// Берем секрет из переменных окружения
		secret := []byte(os.Getenv("JWT_SECRET"))

		token, err := jwt.Parse(tokenString, func(t *jwt.Token) (interface{}, error) {
			return secret, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok {
			// 1. Проверка на блокировку (ТЗ: 418 I'm a teapot)
			if blocked, ok := claims["is_blocked"].(bool); ok && blocked {
				w.WriteHeader(http.StatusTeapot)
				w.Write([]byte("User is blocked"))
				return
			}

			// 2. Извлечение данных (с защитой от float64)
			var userID, courseID int
			if val, ok := claims["user_id"].(float64); ok {
				userID = int(val)
			}
			if val, ok := claims["course_id"].(float64); ok {
				courseID = int(val)
			}

			role, _ := claims["role"].(string)

			// Извлекаем массив разрешений (Permissions) из ТЗ
			var perms []string
			if pRaw, ok := claims["permissions"].([]interface{}); ok {
				for _, p := range pRaw {
					if s, ok := p.(string); ok {
						perms = append(perms, s)
					}
				}
			}

			if userID == 0 || role == "" {
				http.Error(w, "Token missing critical data", http.StatusUnauthorized)
				return
			}

			// 3. Записываем всё в контекст
			ctx := r.Context()
			ctx = context.WithValue(ctx, ContextUserID, userID)
			ctx = context.WithValue(ctx, ContextRole, role)
			ctx = context.WithValue(ctx, ContextPermissions, perms)
			ctx = context.WithValue(ctx, ContextCourseID, courseID)

			next.ServeHTTP(w, r.WithContext(ctx))
		} else {
			http.Error(w, "Could not parse claims", http.StatusUnauthorized)
		}
	}
}

// HasPermission — это новый Middleware вместо CheckAuthAndRole.
// Он проверяет наличие конкретного права из ТЗ.
func HasPermission(requiredPerm string, next http.HandlerFunc) http.HandlerFunc {
	return CheckAuth(func(w http.ResponseWriter, r *http.Request) {
		// Если требование пустое — пускаем любого авторизованного
		if requiredPerm == "" {
			next.ServeHTTP(w, r)
			return
		}

		perms, ok := r.Context().Value(ContextPermissions).([]string)
		if !ok {
			http.Error(w, "Permissions not found", http.StatusForbidden)
			return
		}

		found := false
		for _, p := range perms {
			if p == requiredPerm {
				found = true
				break
			}
		}

		if !found {
			http.Error(w, "Forbidden: missing permission "+requiredPerm, http.StatusForbidden)
			return
		}

		next.ServeHTTP(w, r)
	})
}
