import React from "react";
import { Link } from "react-router-dom";

function App() {
    return (
        <body>
            <nav className="sticky py-4 flex justify-between items-center border-b-2">
                <div className="flex w-4/5 mx-auto justify-between items-center">
                    <Link to="/">
                        <h1 className="font-bold text-2xl tracking-wide ">
                            Legal Assistant
                        </h1>
                    </Link>

                    <div className="flex gap-x-12 font-medium ">
                        <Link to="/" className="hover:underline">
                            Home
                        </Link>
                        <Link to="/document" className="hover:underline">
                            Document Upload
                        </Link>

                        <Link to="/auth/login" className="hover:underline">
                            Log In
                        </Link>
                        <Link to="/auth/signup" className="hover:underline">
                            Sign Up
                        </Link>

                        <button
                            // onClick={handleLogout}
                            className="hover:underline"
                        >
                            Log Out
                        </button>
                    </div>
                </div>
            </nav>
        </body>
    );
}

export default App;
