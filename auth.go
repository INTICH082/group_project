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
		// Секрет берем из переменной окружения Render
		secret := []byte(os.Getenv("JWT_SECRET"))

		token, _ := jwt.Parse(tokenString, func(t *jwt.Token) (interface{}, error) {
			return secret, nil
		})

		if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
			// Вытаскиваем все данные
			ctx := context.WithValue(r.Context(), "user_id", int(claims["user_id"].(float64)))
			ctx = context.WithValue(ctx, "role", claims["role"].(string))
			ctx = context.WithValue(ctx, "course_id", int(claims["course_id"].(float64)))

			next.ServeHTTP(w, r.WithContext(ctx))
		} else {
			http.Error(w, "Invalid token", http.StatusUnauthorized)
		}
	}
}
