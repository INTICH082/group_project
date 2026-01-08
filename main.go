package main

import (
	"log"
	"net/http"
)

func main() {
	InitDB()

	mux := http.NewServeMux()

	withLog := func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			log.Printf("➡️  [%s] %s", r.Method, r.URL.String())
			next(w, r)
		}
	}

	// РЕГИСТРАЦИЯ МАРШРУТОВ
	// Пользователи
	mux.HandleFunc("/admin/user/block", withLog(AuthMiddleware("user:block:write", BlockUserHandler)))
	mux.HandleFunc("/user/update-name", withLog(AuthMiddleware("user:fullName:write", ChangeFullNameHandler)))

	// Курсы
	mux.HandleFunc("/courses", withLog(AuthMiddleware("", ListCoursesHandler)))
	mux.HandleFunc("/teacher/course/create", withLog(AuthMiddleware("course:add", CreateCourseHandler)))
	mux.HandleFunc("/teacher/course/enroll", withLog(AuthMiddleware("course:user:add", EnrollHandler)))
	mux.HandleFunc("/teacher/course/delete", withLog(AuthMiddleware("course:del", DeleteCourseHandler)))

	// Вопросы
	mux.HandleFunc("/teacher/question/create", withLog(AuthMiddleware("quest:create", CreateQuestionHandler)))
	mux.HandleFunc("/teacher/question/update", withLog(AuthMiddleware("quest:update", UpdateQuestionHandler)))
	mux.HandleFunc("/teacher/question/delete", withLog(AuthMiddleware("quest:del", DeleteQuestionHandler)))
	mux.HandleFunc("/teacher/question/list", withLog(AuthMiddleware("quest:read", ListAllQuestionsHandler)))
	mux.HandleFunc("/teacher/course/questions", withLog(AuthMiddleware("quest:read", ListCourseQuestionsHandler)))

	// Тесты
	mux.HandleFunc("/teacher/test/create", withLog(AuthMiddleware("course:test:add", CreateTestHandler)))
	mux.HandleFunc("/teacher/test/status", withLog(AuthMiddleware("course:test:write", UpdateTestStatusHandler)))
	mux.HandleFunc("/test/get", withLog(AuthMiddleware("course:read", GetFullTestHandler)))
	mux.HandleFunc("/test/start", withLog(AuthMiddleware("", StartTestHandler)))
	mux.HandleFunc("/test/answer", withLog(AuthMiddleware("", SubmitAnswerHandler)))
	mux.HandleFunc("/test/finish", withLog(AuthMiddleware("", FinishTestHandler)))
	mux.HandleFunc("/teacher/test/questions/reorder", withLog(AuthMiddleware("test:quest:update", UpdateTestQuestionsOrderHandler)))
	mux.HandleFunc("/teacher/test/results", withLog(AuthMiddleware("test:answer:read", ListAllAttemptsHandler)))
	mux.HandleFunc("/course/tests", withLog(AuthMiddleware("course:test:view", ListTestsHandler)))
	// Сервис
	mux.HandleFunc("/health", withLog(HealthCheckHandler))

	port := getPort()
	log.Printf("🚀 API Server started on :%s", port)
	if err := http.ListenAndServe(":"+port, applyCORS(mux)); err != nil {
		log.Fatal(err)
	}
}
