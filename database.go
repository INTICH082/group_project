package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
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
	log.Println("--- Database initialized with New Structure ---")
}

// --- ЛОГИКА ВОПРОСОВ (ВЕРСИОННОСТЬ) ---

func CreateQuestion(title string, text string, options []string, correct int, authorID int) (int, error) {
	optionsJSON, err := json.Marshal(options)
	if err != nil {
		return 0, fmt.Errorf("marshal options: %v", err)
	}

	// Используем COALESCE, чтобы если таблица пуста, вернулся 1, а не ошибка
	var nextID int
	queryID := "SELECT COALESCE(MAX(id), 0) + 1 FROM questions"
	err = db.QueryRow(queryID).Scan(&nextID)
	if err != nil {
		log.Printf("QueryRow MAX(id) error: %v", err)
		return 0, err
	}

	// ВАЖНО: Добавил поле title, так как оно есть в твоем списке колонок!
	query := `INSERT INTO questions (id, version, title, text, options, correct_option, author_id) 
              VALUES ($1, 1, $2, $3, $4, $5, $6) RETURNING id`

	var id int
	err = db.QueryRow(query, nextID, title, text, optionsJSON, correct, authorID).Scan(&id)
	if err != nil {
		log.Printf("Insert question error: %v", err)
		return 0, err
	}
	return id, nil
}

func UpdateQuestion(questionID int, text string, options []string, correct int) error {
	// ТЗ требует: при изменении создаем новую версию
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

// --- ЛОГИКА ПОПЫТОК (START TEST) ---

func StartAttempt(userID int, testID int) (int, error) {
	// 1. Получаем список актуальных версий вопросов для этого теста
	// В ТЗ: при создании попытки замораживаем версии
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
	err = db.QueryRow(`INSERT INTO attempts (user_id, test_id, question_versions) 
                       VALUES ($1, $2, $3) RETURNING id`,
		userID, testID, versionsJSON).Scan(&attemptID)
	if err != nil {
		return 0, err
	}

	// 3. Создаем пустые ответы для каждого вопроса (selected_option = -1)
	for qid, v := range versionsMap {
		db.Exec(`INSERT INTO user_answers (attempt_id, question_id, question_version) 
                 VALUES ($1, $2, $3)`, attemptID, qid, v)
	}

	return attemptID, nil
}

// --- ЛОГИКА ОТВЕТОВ ---

func SubmitAnswer(attemptID, questionID, option int) error {
	// 1. (Опционально) Тут может быть проверка, не завершена ли попытка
	// Но главное — это шаг 2:

	// 2. СОХРАНЕНИЕ ОТВЕТА (этого у тебя, скорее всего, не хватает)
	query := `
		INSERT INTO student_answers (attempt_id, question_id, selected_option)
		VALUES ($1, $2, $3)
		ON CONFLICT DO NOTHING` // Чтобы не дублировать, если студент нажал дважды

	_, err := db.Exec(query, attemptID, questionID, option)
	if err != nil {
		log.Printf("❌ Ошибка записи ответа в БД: %v", err)
		return err
	}

	return nil
}
func CreateTest(courseID int, name string, questionIDs []int) (int, error) {
	// Мы перечисляем 4 колонки:
	// 1. course_id
	// 2. name
	// 3. question_ids (массив в Postgres)
	// 4. is_active (сразу ставим true)
	// Поле id заполнится само (SERIAL), поле is_deleted по умолчанию false.

	query := `
		INSERT INTO tests (course_id, name, question_ids, is_active) 
		VALUES ($1, $2, $3, $4) 
		RETURNING id`

	var id int

	// Передаем ровно 4 аргумента для 4 колонок:
	err := db.QueryRow(
		query,
		courseID,              // $1
		name,                  // $2
		pq.Array(questionIDs), // $3 (превращает []int в {1,2,3} для Postgres)
		true,                  // $4
	).Scan(&id)

	if err != nil {
		// Логируем ошибку, чтобы её было видно в консоли Render
		log.Printf("❌ Ошибка в CreateTest: %v", err)
		return 0, err
	}

	log.Printf("✅ Тест успешно создан с ID: %d", id)
	return id, nil
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
			)
		WHERE id = $1
		RETURNING COALESCE(score, 0)`

	err := db.QueryRow(query, attemptID).Scan(&score)
	if err != nil {
		log.Printf("❌ Ошибка в FinishAttempt: %v", err)
		return 0, err
	}
	return score, nil
}
func SaveAnswer(attemptID, questionID, selectedOption int) error {
	query := `
		INSERT INTO student_answers (attempt_id, question_id, selected_option) 
		VALUES ($1, $2, $3)`

	_, err := db.Exec(query, attemptID, questionID, selectedOption)
	if err != nil {
		log.Printf("❌ Ошибка при сохранении ответа: %v", err)
		return err
	}
	return nil
}
