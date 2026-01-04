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
		secret := []byte(os.Getenv("JWT_SECRET"))

		token, err := jwt.Parse(tokenString, func(t *jwt.Token) (interface{}, error) {
			return secret, nil
		})

		if err != nil || !token.Valid {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
			return
		}

		if claims, ok := token.Claims.(jwt.MapClaims); ok {
			// --- БЕЗОПАСНОЕ ИЗВЛЕЧЕНИЕ (FIX FLOAT64) ---
			var userID, courseID int

			if val, ok := claims["user_id"].(float64); ok {
				userID = int(val)
			}
			if val, ok := claims["course_id"].(float64); ok {
				courseID = int(val)
			}
			role, _ := claims["role"].(string)

			// Если критические данные отсутствуют - не пускаем
			if userID == 0 || role == "" {
				http.Error(w, "Token missing user_id or role", http.StatusUnauthorized)
				return
			}

			// Записываем в контекст
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
		val := r.Context().Value("role")
		userRole, ok := val.(string)
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
			http.Error(w, "Forbidden: insufficient permissions", http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}
