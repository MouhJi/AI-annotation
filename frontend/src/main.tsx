import {createRoot} from "react-dom/client";import {BrowserRouter} from "react-router-dom";import App from "./App";import "./styles.css";

// react-konva owns a separate canvas reconciler. React StrictMode's development-only
// mount/unmount cycle can destroy its Stage while that reconciler is still updating it.
createRoot(document.getElementById("root")!).render(<BrowserRouter><App/></BrowserRouter>);
