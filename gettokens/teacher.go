package main

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func main() {
	// ТОЧНО ТОТ ЖЕ СЕКРЕТ, ЧТО В auth.go
	jwtSecret := []byte("my_secret_key_for_testing_only_do_not_use_in_production")

	claims := jwt.MapClaims{
		"user_id": 2,                                     // ID преподавателя из тестовых данных
		"role":    "teacher",                             // Роль преподавателя
		"exp":     time.Now().Add(24 * time.Hour).Unix(), // 24 часа
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString(jwtSecret)

	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	fmt.Println("=== WORKING TEACHER TOKEN ===")
	fmt.Println(tokenStr)
	fmt.Println("\nUSE IN REST CLIENT:")
	fmt.Printf("Authorization: Bearer %s\n", tokenStr)
	fmt.Println("\nUSER ID: 2 (teacher)")
}
