package main

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func main() {
	// ТОЧНО ТОТ ЖЕ СЕКРЕТ, ЧТО В auth.go
	jwtSecret := []byte("iplaygodotandclaimfun")

	claims := jwt.MapClaims{
		"user_id": 1,                                     // ID админа из тестовых данных
		"role":    "admin",                               // Роль админа
		"exp":     time.Now().Add(24 * time.Hour).Unix(), // 24 часа
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString(jwtSecret)

	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	fmt.Println("=== WORKING ADMIN TOKEN ===")
	fmt.Println(tokenStr)
	fmt.Println("\nUSE IN REST CLIENT:")
	fmt.Printf("Authorization: Bearer %s\n", tokenStr)
	fmt.Println("\nUSER ID: 1 (admin)")
}
