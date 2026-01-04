package main

import (
	"context"
	"net/http"
	"os"
	"strings"

	"github.com/golang-jwt/jwt/v5"
)

func CheckAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			http.Error(w, "Missing token", http.StatusUnauthorized)
			return
		}

		tokenString := strings.TrimPrefix(authHeader, "Bearer ")
		// Убедись, что JWT_SECRET прописан в настройках Render!
		secret := []byte(os.Getenv("JWT_SECRET"))

		token, err := jwt.Parse(tokenString, func(t *jwt.Token) (interface{}, error) {
			return secret, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok {
			// БЕЗОПАСНОЕ ИЗВЛЕЧЕНИЕ ДАННЫХ

			// 1. Извлекаем user_id (защита от float64)
			var userID int
			if val, ok := claims["user_id"].(float64); ok {
				userID = int(val)
			}

			// 2. Извлекаем course_id (защита от float64)
			var courseID int
			if val, ok := claims["course_id"].(float64); ok {
				courseID = int(val)
			}

			// 3. Извлекаем роль
			role, _ := claims["role"].(string)

			// Проверка: если важные данные отсутствуют в токене
			if userID == 0 || role == "" {
				http.Error(w, "Token is missing user_id or role", http.StatusUnauthorized)
				return
			}

			// Записываем в контекст уже чистые типы данных
			ctx := r.Context()
			ctx = context.WithValue(ctx, "user_id", userID)
			ctx = context.WithValue(ctx, "role", role)
			ctx = context.WithValue(ctx, "course_id", courseID)

			next.ServeHTTP(w, r.WithContext(ctx))
		} else {
			http.Error(w, "Could not parse claims", http.StatusUnauthorized)
		}
	}
}

func CheckAuthAndRole(allowedRoles []string, next http.HandlerFunc) http.HandlerFunc {
	return CheckAuth(func(w http.ResponseWriter, r *http.Request) {
		// Достаем роль, будучи уверенными, что это string
		userRole, ok := r.Context().Value("role").(string)
		if !ok {
			http.Error(w, "Role not found", http.StatusForbidden)
			return
		}

		isAllowed := false
		for _, role := range allowedRoles {
			if role == userRole {
				isAllowed = true
				break
			}
		}

		if !isAllowed {
			http.Error(w, "Нет доступа для вашей роли", http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}
