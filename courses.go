package main

import (
	"encoding/json"
	"net/http"
	"strconv"
)

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

func EnrollHandler(w http.ResponseWriter, r *http.Request) {
	cID, _ := strconv.Atoi(r.URL.Query().Get("course_id"))
	uID, _ := strconv.Atoi(r.URL.Query().Get("user_id"))

	if err := EnrollUser(cID, uID); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	w.Write([]byte("User enrolled successfully"))
}

func DeleteCourseHandler(w http.ResponseWriter, r *http.Request) {
	id, _ := strconv.Atoi(r.URL.Query().Get("id"))
	DeleteCourse(id)
	w.Write([]byte("Course archived"))
}
