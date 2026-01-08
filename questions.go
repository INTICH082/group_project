package main

import (
	"encoding/json"
	"net/http"
	"strconv"
)

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
	json.NewDecoder(r.Body).Decode(&req)

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
	questions, err := GetQuestionsByCourse(courseID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	json.NewEncoder(w).Encode(questions)
}
