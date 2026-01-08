package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

func main() {
	apiUrl := "https://my-app-logic.onrender.com"
	jwtSecret := []byte("iplaygodotandclaimfun")
	tokenStr, _ := generateToken(jwtSecret, 10, "teacher", 1)

	fmt.Println("🚀 ЗАПУСК ТЕСТА (Авто-повтор только при просыпании)")

	// --- ШАГ 1 ---
	fmt.Print("\n[1] Список ДО... ")
	persistentRequest(apiUrl+"/questions", "GET", tokenStr, nil)

	// --- ШАГ 2 ---
	newQ := []byte(`{"text": "Временный вопрос", "options": ["Да", "Нет"], "correct": 0}`)
	fmt.Print("[2] Создание... ")
	respBody := persistentRequest(apiUrl+"/teacher/create", "POST", tokenStr, newQ)

	var created struct{ Id int }
	json.Unmarshal(respBody, &created)
	qID := created.Id

	if qID > 0 {
		// --- ШАГ 3 ---
		fmt.Printf("[3] Проверка ID %d... ", qID)
		persistentRequest(apiUrl+"/questions", "GET", tokenStr, nil)

		// --- ШАГ 4 ---
		fmt.Printf("[4] Удаление ID %d... ", qID)
		deleteUrl := fmt.Sprintf("%s/teacher/delete?id=%d", apiUrl, qID)
		persistentRequest(deleteUrl, "DELETE", tokenStr, nil)

		// --- ШАГ 5 ---
		fmt.Print("[5] Финал... ")
		persistentRequest(apiUrl+"/questions", "GET", tokenStr, nil)
	}

	fmt.Println("\n✨ Готово!")
}

func persistentRequest(url string, method string, token string, body []byte) []byte {
	client := &http.Client{Timeout: 10 * time.Second}

	for {
		req, _ := http.NewRequest(method, url, bytes.NewBuffer(body))
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			// Сервер совсем лежит (Network Error) - молчим и ждем
			time.Sleep(2 * time.Second)
			continue
		}

		respBody, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		// Если сервер выдал 502/503 (Render просыпается) - молчим и ждем
		if resp.StatusCode == 502 || resp.StatusCode == 503 {
			time.Sleep(2 * time.Second)
			continue
		}

		// Если сервер выдал 404 или другую логическую ошибку - пишем и ВЫХОДИМ из цикла
		// чтобы не висеть вечно, если вопроса реально нет
		if resp.StatusCode >= 400 {
			fmt.Printf("❌ Ошибка %d: %s\n", resp.StatusCode, string(respBody))
			return respBody
		}

		// Только при успехе (2xx)
		fmt.Printf("✅ %s\n", string(respBody))
		return respBody
	}
}

func generateToken(secret []byte, uid int, role string, cid int) (string, error) {
	claims := jwt.MapClaims{
		"user_id": uid, "role": role, "course_id": cid,
		"exp": time.Now().Add(time.Hour * 24).Unix(),
	}
	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(secret)
}
