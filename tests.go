package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strconv"

	"github.com/lib/pq"
)

func CreateTestHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		CourseID    int    `json:"course_id"`
		Name        string `json:"name"`
		QuestionIDs []int  `json:"question_ids"`
	}
	json.NewDecoder(r.Body).Decode(&req)
	id, err := CreateTest(req.CourseID, req.Name, req.QuestionIDs)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(map[string]int{"test_id": id})
}

func StartTestHandler(w http.ResponseWriter, r *http.Request) {
	userID := r.Context().Value(ContextUserID).(int)
	testID, _ := strconv.Atoi(r.URL.Query().Get("test_id"))
	attemptID, err := StartAttempt(userID, testID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	json.NewEncoder(w).Encode(map[string]int{"attempt_id": attemptID})
}

func SubmitAnswerHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		AttemptID  int `json:"attempt_id"`
		QuestionID int `json:"question_id"`
		Option     int `json:"selected_option"`
	}
	json.NewDecoder(r.Body).Decode(&req)
	SubmitAnswer(req.AttemptID, req.QuestionID, req.Option)
	w.Write([]byte("Answer saved"))
}

func FinishTestHandler(w http.ResponseWriter, r *http.Request) {
	attID, _ := strconv.Atoi(r.URL.Query().Get("attempt_id"))
	score, _ := FinishAttempt(attID)
	json.NewEncoder(w).Encode(map[string]interface{}{"score": score})
}

func UpdateTestStatusHandler(w http.ResponseWriter, r *http.Request) {
	testID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	active, _ := strconv.ParseBool(r.URL.Query().Get("active"))
	SetTestStatus(testID, active)
	fmt.Fprintf(w, "Test %d status set to %v", testID, active)
}

func GetFullTestHandler(w http.ResponseWriter, r *http.Request) {
	testID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	test, _ := GetFullTest(testID)
	json.NewEncoder(w).Encode(test)
}

// Добавить один вопрос в тест
func AddQuestionToTestHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		TestID  int `json:"test_id"`
		QuestID int `json:"question_id"`
	}
	json.NewDecoder(r.Body).Decode(&req)
	AddQuestionToTest(req.TestID, req.QuestID)
	w.Write([]byte("Question added"))
}

// Удалить один вопрос из теста
func RemoveQuestionFromTestHandler(w http.ResponseWriter, r *http.Request) {
	tID, _ := strconv.Atoi(r.URL.Query().Get("test_id"))
	qID, _ := strconv.Atoi(r.URL.Query().Get("question_id"))
	RemoveQuestionFromTest(tID, qID)
	w.Write([]byte("Question removed"))
}
func UpdateTestQuestionsOrderHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		TestID int   `json:"test_id"`
		IDs    []int `json:"question_ids"`
	}
	json.NewDecoder(r.Body).Decode(&req)

	// Просто перезаписываем массив целиком
	query := `UPDATE tests SET question_ids = $1 WHERE id = $2`
	_, err := db.Exec(query, pq.Array(req.IDs), req.TestID)
	if err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	w.Write([]byte("Order updated"))
}
func ListAllAttemptsHandler(w http.ResponseWriter, r *http.Request) {
	testID, _ := strconv.Atoi(r.URL.Query().Get("test_id"))

	// Используем Query для получения списка строк
	query := `SELECT user_id, score, is_finished, finished_at FROM attempts WHERE test_id = $1`
	rows, err := db.Query(query, testID)
	if err != nil {
		log.Printf("DB Error: %v", err)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var results []map[string]interface{}
	for rows.Next() {
		var userID int
		var score float64
		var isFinished bool
		var finishedAt interface{} // Используем interface, так как в базе может быть null

		if err := rows.Scan(&userID, &score, &isFinished, &finishedAt); err != nil {
			continue
		}

		results = append(results, map[string]interface{}{
			"user_id":     userID,
			"score":       score,
			"is_finished": isFinished,
			"finished_at": finishedAt,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(results)
}
