import React from "react";
import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Login from "./Pages/Login";
import Signup from "./Pages/Signup";
import Document from "./Pages/Document";
import Chatbot from "./Pages/Chatbot";

function App() {
    return (
        <Routes>
            <Route paht="/" element={<Layout />}>
                <Route index element={<Home />}/>
                <Route path="/upload-legal-doc" element={<Document/>}/>
                <Route path="/chatbot" element={<Chatbot/>}/>
                <Route path="/auth/login" element={<Login />}/>
                <Route path="/auth/signup" element={<Signup />}/>
            </Route>
        </Routes>
    );
}

export default App;
