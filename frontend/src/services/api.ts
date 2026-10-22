import axios from "axios";
import type {InternalAxiosRequestConfig} from "axios";
export const API_URL=import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";
export const authApi=axios.create({baseURL:API_URL,withCredentials:true});
export const api=axios.create({baseURL:API_URL,withCredentials:true});
export type User={id:string;email:string;full_name:string;status:string;email_verified:boolean;created_at:string};
type AuthResult={access_token:string;user:User};
let accessToken:string|null=null;
let currentUser:User|null=null;
let refreshPromise:Promise<AuthResult>|null=null;
const listeners=new Set<(user:User|null)=>void>();
export function setAuth(data:AuthResult|null){accessToken=data?.access_token??null;currentUser=data?.user??null;listeners.forEach(listener=>listener(currentUser));}
export function subscribeAuth(listener:(user:User|null)=>void){listeners.add(listener);listener(currentUser);return ()=>{listeners.delete(listener)}}
export function updateAuthUser(user:User){currentUser=user;listeners.forEach(listener=>listener(user))}
export async function refreshSession():Promise<AuthResult>{
 if(!refreshPromise){
  const refresh=async()=>{const data=(await authApi.post<AuthResult>("/auth/refresh")).data;setAuth(data);return data};
  // Serialize cookie rotations across tabs where Web Locks are supported.
  const run=async():Promise<AuthResult>=>typeof navigator!=="undefined"&&navigator.locks?await navigator.locks.request("annotation-refresh",refresh):await refresh();
  refreshPromise=run().catch(error=>{setAuth(null);throw error}).finally(()=>{refreshPromise=null});
 }
 return refreshPromise;
}
api.interceptors.request.use(config=>{if(accessToken)config.headers.Authorization=`Bearer ${accessToken}`;return config});
api.interceptors.response.use(response=>response,async error=>{
 if(typeof window!=="undefined"&&[403,404].includes(error.response?.status)&&/\/(projects|images|annotations|predictions|storage)\//.test(error.config?.url??""))window.dispatchEvent(new Event("workspace-access-denied"));
 const config=error.config as (InternalAxiosRequestConfig & {_authRetried?:boolean})|undefined;
 if(error.response?.status!==401||!config)return Promise.reject(error);
 if(config._authRetried){setAuth(null);return Promise.reject(error)}
 config._authRetried=true;
 try{await refreshSession();return api.request(config)}catch{setAuth(null);return Promise.reject(error)}
});
export async function signOut(all=false){await api.post(all?"/auth/logout-all":"/auth/logout");setAuth(null)}
export const imageUrl=(path:string)=>`${API_URL.replace(/\/api$/,"")}${path}`;
export function errorMessage(error:unknown,fallback="Request failed"){
 if(axios.isAxiosError(error)){
  const detail=error.response?.data?.detail;
  if(typeof detail==="string")return detail;
  if(Array.isArray(detail))return detail.map((item:{msg?:string})=>item.msg??"Invalid input").join(". ");
  if(!error.response)return "Cannot connect to the server. Check your connection and retry.";
 }
 return fallback;
}
