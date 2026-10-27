import {Navigate,Outlet} from "react-router-dom";
import {getAuthGeneration} from '../services/api';
import {useAuth} from "./AuthProvider";
export default function ProtectedRoute(){const {user,initializing}=useAuth();if(initializing)return <main className="editor-loading">Restoring session…</main>;return user?<Outlet key={getAuthGeneration()}/>:<Navigate to="/login" replace state={null}/>}
export function safeReturnPath(value:unknown){return typeof value==="string"&&value.startsWith("/")&&!value.startsWith("//")&&!/[\u0000-\u0020\\]/.test(value)&& !/^\/(login|register|forgot-password|reset-password|verify-email)/.test(value)?value:"/projects"}
