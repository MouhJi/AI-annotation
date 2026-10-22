import {Navigate,Outlet,useLocation} from "react-router-dom";
import {useAuth} from "./AuthProvider";
export default function ProtectedRoute(){const {user,initializing}=useAuth();const location=useLocation();if(initializing)return <main className="editor-loading">Restoring session…</main>;return user?<Outlet/>:<Navigate to="/login" replace state={{from:location.pathname+location.search}}/>}
export function safeReturnPath(value:unknown){return typeof value==="string"&&value.startsWith("/")&&!value.startsWith("//")&&!/[\u0000-\u0020\\]/.test(value)&& !/^\/(login|register|forgot-password|reset-password|verify-email)/.test(value)?value:"/projects"}
