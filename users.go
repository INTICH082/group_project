package main

import (
	"fmt"
	"net/http"
	"strconv"
)

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

	if targetID != currentUserID {
		http.Error(w, "You can only change your own name", 403)
		return
	}

	name := r.URL.Query().Get("name")
	UpdateUserFullName(targetID, name)
	w.Write([]byte("Name updated"))
}
