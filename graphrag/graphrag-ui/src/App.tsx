import "./App.css";
import { Login } from "./components/Login";
import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";

function App() {
  return (
    <>
      <div className="h-[100vh] grid place-items-center">
        <div className="w-full max-w-80">
          <Login />
          <Link
            to="/benchmark"
            className="mt-5 flex items-center justify-between border-t border-border pt-4 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <span>Benchmark comparison</span>
            <ArrowUpRight aria-hidden="true" size={16} />
          </Link>
        </div>
      </div>
    </>
  );
}

export default App;
