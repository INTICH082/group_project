package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/lib/pq"
	_ "github.com/lib/pq"
)

var db *sql.DB

func InitDB() {
	connStr := os.Getenv("DATABASE_URL")
	if connStr == "" {
		log.Fatal("DATABASE_URL is missing")
	}

	var err error
	db, err = sql.Open("postgres", connStr)
	if err != nil {
		log.Fatal(err)
	}

	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	if err = db.Ping(); err != nil {
		log.Fatal("Database unreachable:", err)
	}
	log.Println("--- Database initialized with Full TZ Logic ---")
}

// --- ЛОГИКА ВОПРОСОВ ---

func CreateQuestion(title string, text string, options []string, correct int, authorID int) (int, error) {
	optionsJSON, err := json.Marshal(options)
	if err != nil {
		return 0, fmt.Errorf("marshal options: %v", err)
	}

	var nextID int
	queryID := "SELECT COALESCE(MAX(id), 0) + 1 FROM questions"
	err = db.QueryRow(queryID).Scan(&nextID)
	if err != nil {
		return 0, err
	}

	query := `INSERT INTO questions (id, version, title, text, options, correct_option, author_id) 
              VALUES ($1, 1, $2, $3, $4, $5, $6) RETURNING id`

	var id int
	err = db.QueryRow(query, nextID, title, text, optionsJSON, correct, authorID).Scan(&id)
	return id, err
}

func UpdateQuestion(questionID int, text string, options []string, correct int) error {
	var currentVersion int
	err := db.QueryRow("SELECT MAX(version) FROM questions WHERE id = $1", questionID).Scan(&currentVersion)
	if err != nil {
		return err
	}

	optionsJSON, _ := json.Marshal(options)
	query := `INSERT INTO questions (id, version, text, options, correct_option, author_id) 
              SELECT id, $2, $3, $4, $5, author_id FROM questions 
              WHERE id = $1 AND version = $6`

	_, err = db.Exec(query, questionID, currentVersion+1, text, optionsJSON, correct, currentVersion)
	return err
}

// ТЗ: Удаление вопроса (is_deleted = true)
func DeleteQuestion(questionID int) error {
	_, err := db.Exec("UPDATE questions SET is_deleted = true WHERE id = $1", questionID)
	return err
}

// --- ЛОГИКА ТЕСТОВ ---

func CreateTest(courseID int, name string, questionIDs []int) (int, error) {
	var id int
	// Давай добавим логирование ошибки, чтобы она ТОЧНО появилась в Render Logs
	query := `INSERT INTO tests (course_id, name, question_ids, is_active) VALUES ($1, $2, $3, false) RETURNING id`

	err := db.QueryRow(query, courseID, name, pq.Array(questionIDs)).Scan(&id)
	if err != nil {
		log.Printf("!!! ОШИБКА В CreateTest: %v", err) // Ищи это в логах Render!
		return 0, err
	}
	return id, nil
}

// ТЗ: Активация/Деактивация + авто-завершение попыток
func SetTestStatus(testID int, active bool) error {
	_, err := db.Exec("UPDATE tests SET is_active = $1 WHERE id = $2", active, testID)
	if err != nil {
		return err
	}

	// ТЗ: "Если тест НЕ активный, все начатые попытки автоматически завершаются"
	if !active {
		_, err = db.Exec("UPDATE attempts SET is_finished = true, finished_at = NOW() WHERE test_id = $1 AND is_finished = false", testID)
	}
	return err
}

// --- ЛОГИКА ПОПЫТОК ---

func StartAttempt(userID int, testID int) (int, error) {
	// ТЗ: Проверка, активен ли тест
	var isActive bool
	err := db.QueryRow("SELECT is_active FROM tests WHERE id = $1 AND is_deleted = false", testID).Scan(&isActive)
	if err != nil {
		return 0, fmt.Errorf("тест не найден")
	}
	if !isActive {
		return 0, fmt.Errorf("тест не активен")
	}

	// 1. Замораживаем версии вопросов
	queryVersions := `
        SELECT q.id, MAX(q.version) 
        FROM questions q
        JOIN (SELECT unnest(question_ids) as qid FROM tests WHERE id = $1) t ON q.id = t.qid
        WHERE q.is_deleted = false
        GROUP BY q.id`

	rows, err := db.Query(queryVersions, testID)
	if err != nil {
		return 0, err
	}
	defer rows.Close()

	versionsMap := make(map[int]int)
	for rows.Next() {
		var qid, v int
		rows.Scan(&qid, &v)
		versionsMap[qid] = v
	}
	versionsJSON, _ := json.Marshal(versionsMap)

	// 2. Создаем запись попытки
	var attemptID int
	err = db.QueryRow(`INSERT INTO attempts (user_id, test_id, question_versions, is_finished) 
                       VALUES ($1, $2, $3, false) RETURNING id`,
		userID, testID, versionsJSON).Scan(&attemptID)

	return attemptID, err
}

// --- ЛОГИКА ОТВЕТОВ ---

func SubmitAnswer(attemptID, questionID, selectedOption int) error {
	var isFinished bool
	err := db.QueryRow("SELECT is_finished FROM attempts WHERE id = $1", attemptID).Scan(&isFinished)
	if err != nil {
		return err
	}
	if isFinished {
		return fmt.Errorf("попытка уже завершена")
	}

	query := `
        INSERT INTO student_answers (attempt_id, question_id, selected_option) 
        VALUES ($1, $2, $3)
        ON CONFLICT (attempt_id, question_id) 
        DO UPDATE SET selected_option = $3` // ТЗ: "изменяет значение ответа"

	_, err = db.Exec(query, attemptID, questionID, selectedOption)
	return err
}

func FinishAttempt(attemptID int) (float64, error) {
	var score float64

	query := `
        UPDATE attempts
        SET 
            is_finished = true,
            finished_at = NOW(),
            score = (
                SELECT 
                    (COUNT(CASE WHEN sa.selected_option = q.correct_option THEN 1 END)::float / 
                    NULLIF((SELECT array_length(question_ids, 1) FROM tests WHERE id = attempts.test_id), 0)) * 100
                FROM student_answers sa
                JOIN questions q ON sa.question_id = q.id
                WHERE sa.attempt_id = attempts.id
                -- ВАЖНО: Считаем по последним версиям на момент создания попытки
                AND q.version = (SELECT (question_versions->>(q.id::text))::int FROM attempts WHERE id = $1)
            )
        WHERE id = $1
        RETURNING COALESCE(score, 0)`

	err := db.QueryRow(query, attemptID).Scan(&score)
	return score, err
}

// Хендлер для создания теста (ТЗ: Ресурс Дисциплина -> Добавить тест)
func CreateTestHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		CourseID    int    `json:"course_id"`
		Name        string `json:"name"`
		QuestionIDs []int  `json:"question_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad JSON", http.StatusBadRequest)
		return
	}

	id, err := CreateTest(req.CourseID, req.Name, req.QuestionIDs)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"id": id})
}

// Хендлер для отправки ответа (ТЗ: Ресурс Ответы -> Изменить)
