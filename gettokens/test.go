package main

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func main() {
	// ИСПОЛЬЗУЙ ТОЧНО ЭТОТ СЕКРЕТ ИЗ ТВОЕГО auth.go
	jwtSecret := []byte("my_secret_key_for_testing_only_do_not_use_in_production")

	claims := jwt.MapClaims{
		"user_id": 3,
		"role":    "student",
		"exp":     time.Now().Add(24 * time.Hour).Unix(), // 24 часа
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	tokenStr, err := token.SignedString(jwtSecret)

	if err != nil {
		fmt.Printf("Error: %v\n", err)
		return
	}

	fmt.Println("=== WORKING STUDENT TOKEN ===")
	fmt.Println(tokenStr)
	fmt.Println("\nUse this in Thunder Client:")
	fmt.Printf("Authorization: Bearer %s\n", tokenStr)
}
