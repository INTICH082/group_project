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

// --- ИНИЦИАЛИЗАЦИЯ ---

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
	log.Println("--- Database initialized with Full Logic ---")
}

// --- СТРУКТУРЫ ДАННЫХ ---

type FullTest struct {
	ID        int        `json:"id"`
	Name      string     `json:"name"`
	Questions []Question `json:"questions"`
}

type Question struct {
	ID      int      `json:"id"`
	Title   string   `json:"title"`
	Text    string   `json:"text"`
	Options []string `json:"options"`
	Correct int      `json:"correct"`
}

// --- ЛОГИКА ВОПРОСОВ ---

func CreateQuestion(title string, text string, options []string, correct int, authorID int) (int, error) {
	optionsJSON, _ := json.Marshal(options)
	var id int

	// Сначала получаем следующий ID из последовательности
	err := db.QueryRow("SELECT nextval('questions_id_seq')").Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("ошибка генерации ID: %v", err)
	}

	// Теперь вставляем вопрос с этим ID и версией 1
	query := `
		INSERT INTO questions (id, version, title, text, options, correct_option, author_id, is_deleted) 
		VALUES ($1, 1, $2, $3, $4, $5, $6, false) 
		RETURNING id`

	err = db.QueryRow(query, id, title, text, optionsJSON, correct, authorID).Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("ошибка вставки вопроса: %v", err)
	}
	return id, nil
}

func UpdateQuestion(questionID int, text string, options []string, correct int) error {
	var title string
	var authorID, currentVersion int

	// Проверяем существование вопроса ПЕРЕД обновлением
	err := db.QueryRow(`
		SELECT title, author_id, version 
		FROM questions 
		WHERE id = $1 AND is_deleted = false 
		ORDER BY version DESC LIMIT 1`,
		questionID).Scan(&title, &authorID, &currentVersion)

	if err != nil {
		return fmt.Errorf("вопрос с ID %d не найден или удален", questionID)
	}

	optionsJSON, _ := json.Marshal(options)
	tx, _ := db.Begin()

	// Старую версию помечаем как удаленную (или просто "архивную")
	tx.Exec("UPDATE questions SET is_deleted = true WHERE id = $1 AND version = $2", questionID, currentVersion)

	// Вставляем новую версию с тем же ID, но version+1
	_, err = tx.Exec(`
		INSERT INTO questions (id, version, title, text, options, correct_option, author_id, is_deleted) 
		VALUES ($1, $2, $3, $4, $5, $6, $7, false)`,
		questionID, currentVersion+1, title, text, optionsJSON, correct, authorID)

	if err != nil {
		tx.Rollback()
		return err
	}
	return tx.Commit()
}

func DeleteQuestion(questionID int) error {
	var exists bool
	checkQuery := `SELECT EXISTS(SELECT 1 FROM tests WHERE $1 = ANY(question_ids))`
	db.QueryRow(checkQuery, questionID).Scan(&exists)

	if exists {
		return fmt.Errorf("нельзя удалить: вопрос используется в тестах")
	}

	_, err := db.Exec("UPDATE questions SET is_deleted = true WHERE id = $1", questionID)
	return err
}

// --- ЛОГИКА ТЕСТОВ ---

func CreateTest(courseID int, name string, questionIDs []int) (int, error) {
	var id int
	query := `
        INSERT INTO tests (course_id, name, question_ids, is_active) 
        VALUES ($1, $2, $3::int[], false) 
        RETURNING id`

	err := db.QueryRow(query, courseID, name, pq.Array(questionIDs)).Scan(&id)
	return id, err
}

func UpdateTest(testID int, name string, questionIDs []int, isActive bool) error {
	query := `
		UPDATE tests 
		SET name = $2, question_ids = $3, is_active = $4 
		WHERE id = $1 AND is_deleted = false`

	_, err := db.Exec(query, testID, name, pq.Array(questionIDs), isActive)
	return err
}

func SetTestStatus(testID int, active bool) error {
	tx, err := db.Begin()
	if err != nil {
		return err
	}

	_, err = tx.Exec("UPDATE tests SET is_active = $1 WHERE id = $2", active, testID)
	if err != nil {
		tx.Rollback()
		return err
	}

	if !active {
		tx.Exec("UPDATE attempts SET is_finished = true WHERE test_id = $1 AND is_finished = false", testID)
	}

	return tx.Commit()
}

func GetFullTest(testID int) (*FullTest, error) {
	var t FullTest
	var qIds pq.Int64Array

	err := db.QueryRow("SELECT id, name, question_ids FROM tests WHERE id = $1", testID).Scan(&t.ID, &t.Name, &qIds)
	if err != nil {
		return nil, err
	}

	if len(qIds) > 0 {
		rows, err := db.Query("SELECT id, title, text, options, correct_option FROM questions WHERE id = ANY($1) AND is_deleted = false", qIds)
		if err != nil {
			return nil, err
		}
		defer rows.Close()

		for rows.Next() {
			var q Question
			var opts []byte
			if err := rows.Scan(&q.ID, &q.Title, &q.Text, &opts, &q.Correct); err == nil {
				json.Unmarshal(opts, &q.Options)
				t.Questions = append(t.Questions, q)
			}
		}
	}
	return &t, nil
}

// --- ЛОГИКА ПРОХОЖДЕНИЯ ---

func StartAttempt(userID int, testID int) (int, error) {
	var qIds pq.Int64Array
	// 1. Берем список вопросов из теста
	err := db.QueryRow("SELECT question_ids FROM tests WHERE id = $1 AND is_active = true", testID).Scan(&qIds)
	if err != nil {
		return 0, fmt.Errorf("тест не найден или не активен")
	}

	// 2. Собираем актуальные версии этих вопросов (ТЗ: фиксируем версии при старте)
	versionsMap := make(map[string]int)
	for _, qid := range qIds {
		var v int
		db.QueryRow("SELECT MAX(version) FROM questions WHERE id = $1", qid).Scan(&v)
		versionsMap[fmt.Sprintf("%d", qid)] = v
	}
	versionsJSON, _ := json.Marshal(versionsMap)

	tx, _ := db.Begin()
	var attemptID int

	// 3. Вставляем JSON с версиями в колонку question_versions
	query := `INSERT INTO attempts (user_id, test_id, question_versions, is_finished) 
	          VALUES ($1, $2, $3, false) RETURNING id`

	err = tx.QueryRow(query, userID, testID, versionsJSON).Scan(&attemptID)
	if err != nil {
		tx.Rollback()
		return 0, err
	}

	// 4. Создаем пустые ответы
	for _, qid := range qIds {
		tx.Exec("INSERT INTO student_answers (attempt_id, question_id, selected_option) VALUES ($1, $2, -1)", attemptID, qid)
	}

	return attemptID, tx.Commit()
}

func SubmitAnswer(attemptID int, questionID int, option int) error {
	res, err := db.Exec(`UPDATE student_answers SET selected_option = $3 WHERE attempt_id = $1 AND question_id = $2`, attemptID, questionID, option)
	if err != nil {
		return err
	}
	rows, _ := res.RowsAffected()
	if rows == 0 {
		return fmt.Errorf("ответ не найден")
	}
	return nil
}

func FinishAttempt(attemptID int) (float64, error) {
	var score float64
	// SQL запрос соотносит ответы студента с правильными ответами ТЕХ ВЕРСИЙ, которые были при старте
	query := `
		UPDATE attempts a
		SET is_finished = true, 
		    finished_at = NOW(),
		    score = (
		        SELECT (COUNT(CASE WHEN sa.selected_option = q.correct_option THEN 1 END)::float / 
		                NULLIF(COUNT(sa.id), 0)) * 100
		        FROM student_answers sa
		        JOIN questions q ON sa.question_id = q.id
		        WHERE sa.attempt_id = a.id
		          AND q.version = (a.question_versions->>(q.id::text))::int
		    )
		WHERE id = $1 RETURNING COALESCE(score, 0)`

	err := db.QueryRow(query, attemptID).Scan(&score)
	return score, err
}

// --- УПРАВЛЕНИЕ КУРСАМИ ---

func EnrollUser(courseID int, userID int) error {
	_, err := db.Exec(`INSERT INTO course_users (course_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING`, courseID, userID)
	return err
}

func UnenrollUser(courseID int, userID int) error {
	_, err := db.Exec("DELETE FROM course_users WHERE course_id = $1 AND user_id = $2", courseID, userID)
	return err
}

func IsUserEnrolled(courseID int, userID int) (bool, error) {
	var exists bool
	err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM course_users WHERE course_id = $1 AND user_id = $2)", courseID, userID).Scan(&exists)
	return exists, err
}

func AddQuestionToTest(testID, questionID int) error {
	res, err := db.Exec(`
        UPDATE tests 
        SET question_ids = array_append(COALESCE(question_ids, '{}'::int[]), $1) 
        WHERE id = $2 AND is_deleted = false`,
		questionID, testID)
	if err != nil {
		return err
	}
	rows, _ := res.RowsAffected()
	if rows == 0 {
		return fmt.Errorf("тест не найден")
	}
	return nil
}

func RemoveQuestionFromTest(testID, questionID int) error {
	res, err := db.Exec(`UPDATE tests SET question_ids = array_remove(question_ids, $1) WHERE id = $2 AND is_deleted = false`, questionID, testID)
	if err != nil {
		return err
	}
	rows, _ := res.RowsAffected()
	if rows == 0 {
		return fmt.Errorf("тест не найден")
	}
	return nil
}

func GetTestsByCourse(courseID int) ([]map[string]interface{}, error) {
	rows, err := db.Query("SELECT id, name, is_active, COALESCE(question_ids, '{}'::int[]) FROM tests WHERE course_id = $1 AND is_deleted = false", courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []map[string]interface{}
	for rows.Next() {
		var id int
		var name string
		var active bool
		var qIds pq.Int64Array

		rows.Scan(&id, &name, &active, &qIds)

		ids := make([]int, len(qIds))
		for i, v := range qIds {
			ids[i] = int(v)
		}

		results = append(results, map[string]interface{}{
			"id":           id,
			"name":         name,
			"is_active":    active,
			"question_ids": ids,
		})
	}
	return results, nil
}

// --- РЕСУРС: ПОЛЬЗОВАТЕЛИ (Auth/Admin логика) ---

func SetUserBlockStatus(targetID int, blocked bool) error {
	// ТЗ: При блокировке пользователю запрещены все действия
	_, err := db.Exec("UPDATE users SET is_blocked = $1 WHERE id = $2", blocked, targetID)
	return err
}

func UpdateUserRoles(targetID int, roles []string) error {
	rolesJSON, _ := json.Marshal(roles)
	_, err := db.Exec("UPDATE users SET roles = $1 WHERE id = $2", rolesJSON, targetID)
	return err
}

func UpdateUserFullName(targetID int, fullName string) error {
	_, err := db.Exec("UPDATE users SET full_name = $1 WHERE id = $2", fullName, targetID)
	return err
}

// --- РЕСУРС: ДИСЦИПЛИНЫ ---

func CreateCourse(name, description string, teacherID int) (int, error) {
	var id int
	// ОБЯЗАТЕЛЬНО: RETURNING id в конце запроса
	query := `INSERT INTO courses (name, description, teacher_id) VALUES ($1, $2, $3) RETURNING id`
	err := db.QueryRow(query, name, description, teacherID).Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("ошибка создания курса: %v", err)
	}
	return id, nil
}

func DeleteCourse(courseID int) error {
	// ТЗ: Реально ничего не удаляется, просто помечается удаленным
	_, err := db.Exec("UPDATE courses SET is_deleted = true WHERE id = $1", courseID)
	return err
}

func GetAllCourses() ([]map[string]interface{}, error) {
	rows, err := db.Query("SELECT id, name, description, teacher_id FROM courses WHERE is_deleted = false")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var courses []map[string]interface{}
	for rows.Next() {
		var id, tID int
		var name, desc string
		rows.Scan(&id, &name, &desc, &tID)
		courses = append(courses, map[string]interface{}{
			"id": id, "name": name, "description": desc, "teacher_id": tID,
		})
	}
	return courses, nil
}

// --- НОВЫЕ ФУНКЦИИ ЛОГИКИ ВОПРОСОВ ---

// GetAllQuestions возвращает вообще все активные вопросы в системе
func GetAllQuestions() ([]Question, error) {
	rows, err := db.Query(`
		SELECT id, title, text, options, correct_option 
		FROM questions 
		WHERE is_deleted = false 
		ORDER BY id DESC`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	return scanQuestions(rows)
}

// GetQuestionsByCourse возвращает вопросы, которые используются в тестах конкретного курса
func GetQuestionsByCourse(courseID int) ([]Question, error) {
	query := `
		SELECT DISTINCT q.id, q.title, q.text, q.options, q.correct_option 
		FROM questions q
		JOIN tests t ON q.id = ANY(t.question_ids)
		WHERE t.course_id = $1 AND q.is_deleted = false AND t.is_deleted = false
		ORDER BY q.id DESC`

	rows, err := db.Query(query, courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	return scanQuestions(rows)
}

// Вспомогательная функция для сканирования строк (DRY)
func scanQuestions(rows *sql.Rows) ([]Question, error) {
	var questions []Question
	for rows.Next() {
		var q Question
		var opts []byte
		if err := rows.Scan(&q.ID, &q.Title, &q.Text, &opts, &q.Correct); err != nil {
			return nil, err
		}
		json.Unmarshal(opts, &q.Options)
		questions = append(questions, q)
	}
	return questions, nil
}
