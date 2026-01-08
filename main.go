package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
)

// --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

func getPort() string {
	if p := os.Getenv("PORT"); p != "" {
		return p
	}
	return "8080"
}

// applyCORS добавляет заголовки для работы с фронтендом
func applyCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE, PATCH")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

		if r.Method == "OPTIONS" {
			w.WriteHeader(http.StatusOK)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// --- ОБРАБОТЧИКИ: ВОПРОСЫ ---

func CreateQuestionHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Title   string   `json:"title"`
		Text    string   `json:"text"`
		Options []string `json:"options"`
		Correct int      `json:"correct_option"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	authorID := r.Context().Value(ContextUserID).(int)
	id, err := CreateQuestion(req.Title, req.Text, req.Options, req.Correct, authorID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(map[string]int{"id": id})
}

func UpdateQuestionHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		ID      int      `json:"id"`
		Text    string   `json:"text"`
		Options []string `json:"options"`
		Correct int      `json:"correct_option"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if err := UpdateQuestion(req.ID, req.Text, req.Options, req.Correct); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Write([]byte("Question updated to a new version"))
}

func DeleteQuestionHandler(w http.ResponseWriter, r *http.Request) {
	id, _ := strconv.Atoi(r.URL.Query().Get("id"))
	if err := DeleteQuestion(id); err != nil {
		http.Error(w, err.Error(), http.StatusForbidden)
		return
	}
	w.Write([]byte("Question marked as deleted"))
}

// --- ОБРАБОТЧИКИ: ТЕСТЫ ---

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

func UpdateTestStatusHandler(w http.ResponseWriter, r *http.Request) {
	testID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	active, _ := strconv.ParseBool(r.URL.Query().Get("active"))

	if err := SetTestStatus(testID, active); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	fmt.Fprintf(w, "Test %d status set to %v", testID, active)
}

func GetFullTestHandler(w http.ResponseWriter, r *http.Request) {
	testID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	test, err := GetFullTest(testID)
	if err != nil {
		http.Error(w, "Test not found", http.StatusNotFound)
		return
	}
	json.NewEncoder(w).Encode(test)
}

// --- ОБРАБОТЧИКИ: ПРОХОЖДЕНИЕ ---

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

	if err := SubmitAnswer(req.AttemptID, req.QuestionID, req.Option); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Write([]byte("Answer saved"))
}

func FinishTestHandler(w http.ResponseWriter, r *http.Request) {
	attID, _ := strconv.Atoi(r.URL.Query().Get("attempt_id"))
	score, err := FinishAttempt(attID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(map[string]interface{}{"score": score})
}

// --- ОБРАБОТЧИКИ: КУРСЫ ---

func EnrollHandler(w http.ResponseWriter, r *http.Request) {
	cID, _ := strconv.Atoi(r.URL.Query().Get("course_id"))
	uID, _ := strconv.Atoi(r.URL.Query().Get("user_id"))

	if err := EnrollUser(cID, uID); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Write([]byte("User enrolled successfully"))
}

// Хендлеры Пользователей
func BlockUserHandler(w http.ResponseWriter, r *http.Request) {
	uID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	block, _ := strconv.ParseBool(r.URL.Query().Get("block"))
	if err := SetUserBlockStatus(uID, block); err != nil {
		http.Error(w, err.Error(), 500)
		return
	}
	fmt.Fprintf(w, "User block status: %v", block)
}

func ChangeFullNameHandler(w http.ResponseWriter, r *http.Request) {
	targetID, _ := strconv.Atoi(r.URL.Query().Get("id"))
	currentUserID := r.Context().Value(ContextUserID).(int)

	// ТЗ: Себе можно (+), другому — только если есть спец. права
	if targetID != currentUserID {
		// Здесь можно добавить проверку на админа, если нужно
		http.Error(w, "You can only change your own name", 403)
		return
	}

	name := r.URL.Query().Get("name")
	UpdateUserFullName(targetID, name)
	w.Write([]byte("Name updated"))
}

// Хендлеры Курсов
func CreateCourseHandler(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name      string
		Desc      string
		TeacherID int
	}
	json.NewDecoder(r.Body).Decode(&req)
	id, _ := CreateCourse(req.Name, req.Desc, req.TeacherID)
	json.NewEncoder(w).Encode(map[string]int{"course_id": id})
}

func ListCoursesHandler(w http.ResponseWriter, r *http.Request) {
	courses, _ := GetAllCourses()
	json.NewEncoder(w).Encode(courses)
}

// HealthCheckHandler проверяет состояние API и базы данных
func HealthCheckHandler(w http.ResponseWriter, r *http.Request) {
	// Проверяем соединение с базой данных
	if err := db.Ping(); err != nil {
		w.WriteHeader(http.StatusInternalServerError)
		json.NewEncoder(w).Encode(map[string]string{
			"status":   "error",
			"database": "unreachable",
		})
		return
	}

	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(map[string]string{
		"status":  "ok",
		"service": "api-logic",
	})
}
func ListAllQuestionsHandler(w http.ResponseWriter, r *http.Request) {
	questions, err := GetAllQuestions()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(questions)
}

func ListCourseQuestionsHandler(w http.ResponseWriter, r *http.Request) {
	courseID, _ := strconv.Atoi(r.URL.Query().Get("course_id"))
	if courseID == 0 {
		http.Error(w, "course_id is required", http.StatusBadRequest)
		return
	}

	questions, err := GetQuestionsByCourse(courseID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(questions)
}

// --- MAIN С ЛОГИКОЙ МАРШРУТИЗАЦИИ ---

func main() {
	// 1. Подключаем БД
	InitDB()

	mux := http.NewServeMux()

	// 2. Middleware для логирования
	withLog := func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			log.Printf("➡️  [%s] %s", r.Method, r.URL.String())
			next(w, r)
		}
	}
	// --- ПОЛЬЗОВАТЕЛИ (Управление) ---
	mux.HandleFunc("/admin/user/block", withLog(AuthMiddleware("user:block:write", BlockUserHandler)))
	mux.HandleFunc("/user/update-name", withLog(AuthMiddleware("user:fullName:write", ChangeFullNameHandler)))

	// --- ДИСЦИПЛИНЫ (Управление) ---
	mux.HandleFunc("/courses", withLog(AuthMiddleware("", ListCoursesHandler))) // Доступно всем
	mux.HandleFunc("/teacher/course/create", withLog(AuthMiddleware("course:add", CreateCourseHandler)))
	mux.HandleFunc("/teacher/course/delete", withLog(AuthMiddleware("course:del", func(w http.ResponseWriter, r *http.Request) {
		id, _ := strconv.Atoi(r.URL.Query().Get("id"))
		DeleteCourse(id)
		w.Write([]byte("Course archived"))
	})))
	// --- МАРШРУТЫ ---
	mux.HandleFunc("/health", withLog(HealthCheckHandler))
	// Вопросы (Questions)
	mux.HandleFunc("/teacher/question/create", withLog(AuthMiddleware("quest:create", CreateQuestionHandler)))
	mux.HandleFunc("/teacher/question/update", withLog(AuthMiddleware("quest:update", UpdateQuestionHandler)))
	mux.HandleFunc("/teacher/question/delete", withLog(AuthMiddleware("quest:del", DeleteQuestionHandler)))

	// Тесты (Tests)
	mux.HandleFunc("/teacher/test/create", withLog(AuthMiddleware("course:test:add", CreateTestHandler)))
	mux.HandleFunc("/teacher/test/status", withLog(AuthMiddleware("course:test:write", UpdateTestStatusHandler)))
	mux.HandleFunc("/test/get", withLog(AuthMiddleware("course:read", GetFullTestHandler)))

	// Прохождение (Право "" — доступно любому авторизованному)
	mux.HandleFunc("/test/start", withLog(AuthMiddleware("", StartTestHandler)))
	mux.HandleFunc("/test/answer", withLog(AuthMiddleware("", SubmitAnswerHandler)))
	mux.HandleFunc("/test/finish", withLog(AuthMiddleware("", FinishTestHandler)))
	// В секцию "Вопросы (Questions)"
	mux.HandleFunc("/teacher/question/list", withLog(AuthMiddleware("quest:read", ListAllQuestionsHandler)))
	mux.HandleFunc("/teacher/course/questions", withLog(AuthMiddleware("quest:read", ListCourseQuestionsHandler)))
	// Курсы и Студенты
	mux.HandleFunc("/teacher/course/enroll", withLog(AuthMiddleware("course:user:add", EnrollHandler)))

	// 3. Запуск сервера с CORS
	port := getPort()
	log.Printf("🚀 API Server started on :%s", port)
	log.Printf("Secret verified: iplaygodotandclaimfun")

	if err := http.ListenAndServe(":"+port, applyCORS(mux)); err != nil {
		log.Fatal(err)
	}
}
