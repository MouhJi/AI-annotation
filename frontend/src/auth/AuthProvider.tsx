import {createContext,useContext,useEffect,useState,type ReactNode} from "react";
import {getAuthGeneration,loginSession,refreshSession,subscribeAuth,signOut,type User} from "../services/api";
import {useNavigate} from 'react-router-dom';
import IdleSession from './IdleSession';
type AuthContextValue={user:User|null;initializing:boolean;login:(email:string,password:string)=>Promise<User>;logout:(all?:boolean)=>Promise<void>};
const AuthContext=createContext<AuthContextValue|null>(null);
export function AuthProvider({children}:{children:ReactNode}){
 const navigate=useNavigate();
 const [user,setUser]=useState<User|null>(null);const [initializing,setInitializing]=useState(true);
 useEffect(()=>subscribeAuth(setUser),[]);
 useEffect(()=>{let alive=true;void refreshSession().catch(()=>{}).finally(()=>{if(alive)setInitializing(false)});return()=>{alive=false}},[]);
 const logout=(all=false)=>{const pending=signOut(all);navigate('/login',{replace:true,state:null});return pending;};
 return <AuthContext.Provider value={{user,initializing,login:loginSession,logout}}><IdleSession key={getAuthGeneration()}/>{children}</AuthContext.Provider>;
}
export function useAuth(){const context=useContext(AuthContext);if(!context)throw new Error("AuthProvider required");return context}
