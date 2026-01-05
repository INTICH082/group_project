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

// CreateQuestion создает новый вопрос с начальной версией 1.
// ВАЖНО: Мы явно ставим is_deleted = false, чтобы вопрос был виден в тестах.
func CreateQuestion(title string, text string, options []string, correct int, authorID int) (int, error) {
	// 1. Превращаем слайс строк []string в JSON, чтобы Postgres мог его сохранить
	optionsJSON, err := json.Marshal(options)
	if err != nil {
		return 0, fmt.Errorf("ошибка маршалинга options: %v", err)
	}

	// 2. Получаем следующий свободный ID (ручная инкрементация по твоему запросу)
	var nextID int
	queryID := "SELECT COALESCE(MAX(id), 0) + 1 FROM questions"
	err = db.QueryRow(queryID).Scan(&nextID)
	if err != nil {
		return 0, fmt.Errorf("ошибка при получении следующего ID: %v", err)
	}

	// 3. Выполняем вставку.
	// Добавлена колонка is_deleted со значением false ($7).
	query := `
		INSERT INTO questions (
			id, 
			version, 
			title, 
			text, 
			options, 
			correct_option, 
			author_id, 
			is_deleted
		) 
		VALUES ($1, 1, $2, $3, $4, $5, $6, false) 
		RETURNING id`

	var id int
	err = db.QueryRow(
		query,
		nextID,
		title,
		text,
		optionsJSON,
		correct,
		authorID,
	).Scan(&id)

	if err != nil {
		return 0, fmt.Errorf("ошибка при вставке вопроса в БД: %v", err)
	}

	return id, nil
}

func UpdateQuestion(questionID int, text string, options []string, correct int) error {
	// 1. Находим текущую макс. версию
	var currentVersion int
	err := db.QueryRow("SELECT MAX(version) FROM questions WHERE id = $1", questionID).Scan(&currentVersion)
	if err != nil {
		return fmt.Errorf("вопрос не найден: %v", err)
	}

	optionsJSON, _ := json.Marshal(options)

	// Добавляем title в INSERT и SELECT
	query := `
        INSERT INTO questions (id, version, title, text, options, correct_option, author_id, is_deleted) 
        SELECT id, $2, title, $3, $4, $5, author_id, false 
        FROM questions 
        WHERE id = $1 AND version = $6
        RETURNING version`

	var newVer int
	// Обрати внимание: в SELECT мы берем 'title' из старой записи,
	// а $3, $4, $5 — это новые данные (текст, опции, ответ)
	err = db.QueryRow(query, questionID, currentVersion+1, text, optionsJSON, correct, currentVersion).Scan(&newVer)

	if err != nil {
		return fmt.Errorf("ошибка при обновлении вопроса: %v", err)
	}

	return nil
}

func DeleteQuestion(questionID int) error {
	// 1. Проверяем, используется ли вопрос в ЛЮБЫХ тестах
	var exists bool
	checkQuery := `SELECT EXISTS(SELECT 1 FROM tests WHERE $1 = ANY(question_ids))`
	err := db.QueryRow(checkQuery, questionID).Scan(&exists)
	if err != nil {
		return err
	}

	if exists {
		return fmt.Errorf("нельзя удалить: вопрос используется в одном или нескольких тестах")
	}

	// 2. Если не используется — помечаем как удаленный (Soft Delete)
	_, err = db.Exec("UPDATE questions SET is_deleted = true WHERE id = $1", questionID)
	return err
}

func CreateTest(courseID int, name string, questionIDs []int) (int, error) {
	var id int
	// 1. В самом запросе добавь ::int[] для гарантии типа
	query := `
        INSERT INTO tests (course_id, name, question_ids, is_active) 
        VALUES ($1, $2, $3::int[], false) 
        RETURNING id`

	// 2. В Scan передавай ПЕРЕМЕННУЮ, а не создавай новую через :=
	// 3. Используй pq.Array(questionIDs)
	err := db.QueryRow(query, courseID, name, pq.Array(questionIDs)).Scan(&id)

	if err != nil {
		// ЭТО ОЧЕНЬ ВАЖНО: если тут ошибка, мы должны её увидеть
		fmt.Printf("DATABASE ERROR: %v\n", err)
		return 0, err
	}
	return id, nil
}

// ТЗ: Активация/Деактивация + авто-завершение попыток
func SetTestStatus(testID int, active bool) error {
	// ТЗ: Если тест установлен в состояние Не активный (false),
	// все начатые попытки автоматически отмечаются завершёнными.

	tx, err := db.Begin()
	if err != nil {
		return err
	}

	// Обновляем статус теста
	_, err = tx.Exec("UPDATE tests SET is_active = $1 WHERE id = $2", active, testID)
	if err != nil {
		tx.Rollback()
		return err
	}

	// Если мы выключаем тест, закрываем все открытые попытки
	if !active {
		_, err = tx.Exec(`
			UPDATE attempts 
			SET is_finished = true 
			WHERE test_id = $1 AND is_finished = false`,
			testID)
		if err != nil {
			tx.Rollback()
			return err
		}
	}

	return tx.Commit()
}

// --- ЛОГИКА ПОПЫТОК ---

func StartAttempt(userID int, testID int) (int, error) {
	// 1. ТЗ: Проверка, активен ли тест и существует ли он
	var isActive bool
	err := db.QueryRow("SELECT is_active FROM tests WHERE id = $1 AND is_deleted = false", testID).Scan(&isActive)
	if err != nil {
		if err == sql.ErrNoRows {
			return 0, fmt.Errorf("тест не найден")
		}
		return 0, err
	}
	if !isActive {
		return 0, fmt.Errorf("тест не активен")
	}

	// 2. ТЗ: Попытка всегда одна. Проверяем, не начал ли пользователь этот тест ранее.
	var existingID int
	err = db.QueryRow("SELECT id FROM attempts WHERE user_id = $1 AND test_id = $2", userID, testID).Scan(&existingID)
	if err == nil {
		return 0, fmt.Errorf("попытка для этого теста уже существует (ID: %d)", existingID)
	}

	// 3. ТЗ: Выбирается самая последняя версия вопроса.
	// Берем актуальные версии для всех вопросов, входящих в массив теста.
	queryVersions := `
		SELECT q.id, MAX(q.version) 
		FROM questions q
		WHERE q.id IN (SELECT unnest(question_ids) FROM tests WHERE id = $1)
		  AND q.is_deleted = false
		GROUP BY q.id`

	rows, err := db.Query(queryVersions, testID)
	if err != nil {
		return 0, fmt.Errorf("ошибка при получении версий вопросов: %v", err)
	}
	defer rows.Close()

	versionsMap := make(map[int]int)
	var questionIDs []int // Сохраним ID для создания пустых ответов
	for rows.Next() {
		var qid, v int
		if err := rows.Scan(&qid, &v); err != nil {
			return 0, err
		}
		versionsMap[qid] = v
		questionIDs = append(questionIDs, qid)
	}
	versionsJSON, _ := json.Marshal(versionsMap)

	// Начинаем транзакцию, так как нам нужно гарантированно создать и попытку, и ответы
	tx, err := db.Begin()
	if err != nil {
		return 0, err
	}

	// 4. Создаем запись попытки
	var attemptID int
	queryInsertAttempt := `
		INSERT INTO attempts (user_id, test_id, question_versions, is_finished) 
		VALUES ($1, $2, $3, false) 
		RETURNING id`

	err = tx.QueryRow(queryInsertAttempt, userID, testID, versionsJSON).Scan(&attemptID)
	if err != nil {
		tx.Rollback()
		return 0, fmt.Errorf("ошибка создания попытки: %v", err)
	}

	// 5. ТЗ: Ответ автоматически создаётся системой во время создания попытки.
	// Значение по умолчанию -1.
	for _, qid := range questionIDs {
		_, err = tx.Exec(`
			INSERT INTO student_answers (attempt_id, question_id, selected_option) 
			VALUES ($1, $2, -1)`,
			attemptID, qid)

		if err != nil {
			tx.Rollback()
			return 0, fmt.Errorf("ошибка предсоздания ответа для вопроса %d: %v", qid, err)
		}
	}

	// Фиксируем изменения в БД
	if err := tx.Commit(); err != nil {
		return 0, err
	}

	return attemptID, nil
}

// --- ЛОГИКА ОТВЕТОВ ---

func SubmitAnswer(attemptID int, questionID int, option int) error {
	// Просто обновляем уже существующую строку, которую создала StartAttempt
	_, err := db.Exec(`
        UPDATE student_answers 
        SET selected_option = $3 
        WHERE attempt_id = $1 AND question_id = $2`,
		attemptID, questionID, option)
	return err
}

func FinishAttempt(attemptID int) (float64, error) {
	var score float64

	// 1. Сначала просто закрываем попытку и получаем данные для расчета
	// 2. Считаем баллы прямо в UPDATE, используя NULLIF для защиты от деления на 0
	query := `
        UPDATE attempts a
        SET 
            is_finished = true,
            finished_at = NOW(),
            score = (
                SELECT 
                    CASE 
                        WHEN count_total = 0 THEN 0
                        ELSE (count_correct::float / count_total::float) * 100
                    END
                FROM (
                    SELECT 
                        COUNT(*) as count_total,
                        COUNT(CASE WHEN sa.selected_option = q.correct_option THEN 1 END) as count_correct
                    FROM student_answers sa
                    JOIN questions q ON sa.question_id = q.id
                    WHERE sa.attempt_id = a.id
                    AND q.version = (a.question_versions->>(q.id::text))::int
                ) as stats
            )
        WHERE id = $1
        RETURNING COALESCE(score, 0)`

	err := db.QueryRow(query, attemptID).Scan(&score)
	if err != nil {
		return 0, fmt.Errorf("ошибка финализации: %v", err)
	}
	return score, nil
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
func AddQuestionToTest(testID, questionID int) error {
	var count int
	// Считаем количество любых попыток для этого теста
	err := db.QueryRow("SELECT COUNT(*) FROM attempts WHERE test_id = $1", testID).Scan(&count)
	if err != nil {
		return err
	}

	if count > 0 {
		// Если нашли хотя бы одну попытку — возвращаем ошибку
		// Важно: текст ошибки может быть любым, хендлер всё равно отправит 403
		return fmt.Errorf("состав теста заблокирован: найдено %d попыток", count)
	}

	// Если попыток 0 — выполняем обновление
	_, err = db.Exec("UPDATE tests SET question_ids = array_append(question_ids, $1) WHERE id = $2", questionID, testID)
	return err
}
func RemoveQuestionFromTest(testID, questionID int) error {
	var hasAttempts bool
	err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM attempts WHERE test_id = $1)", testID).Scan(&hasAttempts)
	if err != nil {
		return err
	}

	if hasAttempts {
		return fmt.Errorf("forbidden: cannot modify test with existing attempts")
	}

	_, err = db.Exec("UPDATE tests SET question_ids = array_remove(question_ids, $1) WHERE id = $2", questionID, testID)
	return err
}

// EnrollUser записывает студента на курс (course:user:add по ТЗ)
func EnrollUser(courseID int, userID int) error {
	_, err := db.Exec(`
        INSERT INTO course_users (course_id, user_id) 
        VALUES ($1, $2) 
        ON CONFLICT DO NOTHING`, courseID, userID)
	return err
}

// UnenrollUser отчисляет студента (course:user:del по ТЗ)
func UnenrollUser(courseID int, userID int) error {
	_, err := db.Exec("DELETE FROM course_users WHERE course_id = $1 AND user_id = $2", courseID, userID)
	return err
}

// IsUserEnrolled проверяет, имеет ли студент доступ к курсу
func IsUserEnrolled(courseID int, userID int) (bool, error) {
	var exists bool
	err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM course_users WHERE course_id = $1 AND user_id = $2)",
		courseID, userID).Scan(&exists)
	return exists, err
}
func GetTestsByCourse(courseID int) ([]map[string]interface{}, error) {
	// ЗАМЕНЕНО: title -> name
	rows, err := db.Query("SELECT id, name, is_active FROM tests WHERE course_id = $1 AND is_deleted = false", courseID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var results []map[string]interface{}
	for rows.Next() {
		var id int
		var name string // Поменял имя переменной для ясности
		var active bool
		if err := rows.Scan(&id, &name, &active); err != nil {
			return nil, err
		}
		results = append(results, map[string]interface{}{
			"id": id, "title": name, "is_active": active, // Оставляем ключ "title" для фронтенда/теста
		})
	}
	return results, nil
}
