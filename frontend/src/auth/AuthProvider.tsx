import {createContext,useContext,useEffect,useState,type ReactNode} from "react";
import {authApi,refreshSession,setAuth,subscribeAuth,signOut,type User} from "../services/api";
import IdleSession from './IdleSession';
type AuthContextValue={user:User|null;initializing:boolean;login:(email:string,password:string)=>Promise<void>;logout:(all?:boolean)=>Promise<void>};
const AuthContext=createContext<AuthContextValue|null>(null);
export function AuthProvider({children}:{children:ReactNode}){
 const [user,setUser]=useState<User|null>(null);const [initializing,setInitializing]=useState(true);
 useEffect(()=>subscribeAuth(setUser),[]);
 useEffect(()=>{let alive=true;void refreshSession().catch(()=>{}).finally(()=>{if(alive)setInitializing(false)});return()=>{alive=false}},[]);
 const login=async(email:string,password:string)=>{const data=(await authApi.post("/auth/login",{email,password})).data;setAuth(data)};
 return <AuthContext.Provider value={{user,initializing,login,logout:signOut}}><IdleSession/>{children}</AuthContext.Provider>;
}
export function useAuth(){const context=useContext(AuthContext);if(!context)throw new Error("AuthProvider required");return context}
