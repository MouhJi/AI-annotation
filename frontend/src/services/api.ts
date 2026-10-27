import axios from "axios";
import type {InternalAxiosRequestConfig} from "axios";
export const API_URL=import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";
export const authApi=axios.create({baseURL:API_URL,withCredentials:true});
export const api=axios.create({baseURL:API_URL,withCredentials:true});
export type User={id:string;email:string;full_name:string;status:string;email_verified:boolean;is_platform_admin?:boolean;created_at:string};
export type SessionPolicy={id:string;server_time:string;idle_expires_at:string;idle_timeout_seconds:number;warning_seconds:number};
export type AuthResult={access_token:string;user:User;session?:SessionPolicy};
let sessionPolicy:SessionPolicy|null=null;
let authGeneration=0;
export const getSessionPolicy=()=>sessionPolicy;
export const getAuthGeneration=()=>authGeneration;
let accessToken:string|null=null;
let currentUser:User|null=null;
let refreshPromise:Promise<AuthResult>|null=null;
let logoutPromise:Promise<void>|null=null;
let authQueue:Promise<unknown>=Promise.resolve();
const listeners=new Set<(user:User|null)=>void>();
const sessionEnded=()=>new axios.CanceledError("The account session changed. Please retry.");

function clearAccountStorage(){
  // Remove only application account/navigation state, not unrelated site settings.
  for(const storage of [localStorage,sessionStorage]){
    if(currentUser)storage.removeItem('workspace:'+currentUser.id);
    for(const key of ['returnTo','redirectTo','from'])storage.removeItem(key);
  }
}
export function setAuth(data:AuthResult|null){
  const changed=!!data&&!!currentUser&&(data.user.id!==currentUser.id||
    (!!sessionPolicy&&!!data.session&&sessionPolicy.id!==data.session.id));
  if(!data||changed){
    authGeneration++;refreshPromise=null;
    try{clearAccountStorage();}catch{/* Authentication still clears when storage is unavailable. */}
  }
  accessToken=data?.access_token??null;currentUser=data?.user??null;
  sessionPolicy=data?.session??null;
  if(sessionPolicy)window.dispatchEvent(new CustomEvent('session-policy',{detail:sessionPolicy}));
  listeners.forEach(listener=>listener(currentUser));
}
export function subscribeAuth(listener:(user:User|null)=>void){listeners.add(listener);listener(currentUser);return ()=>{listeners.delete(listener)}}
export function updateAuthUser(user:User){
  if(!currentUser||currentUser.id!==user.id)return;
  currentUser=user;listeners.forEach(listener=>listener(user));
}
function authRequest<T>(run:()=>Promise<T>):Promise<T>{
  // Serialize cookie writes locally and across tabs. A late refresh/logout must
  // finish before a new login sets its cookie.
  const next=authQueue.catch(()=>{}).then(async()=>typeof navigator!=="undefined"&&navigator.locks
    ?await navigator.locks.request("annotation-refresh",run):await run());
  authQueue=next.catch(()=>{});
  return next;
}
export async function loginSession(email:string,password:string):Promise<User>{
  setAuth(null);
  const generation=authGeneration;
  return authRequest(async()=>{
    if(generation!==authGeneration)throw sessionEnded();
    const data=(await authApi.post<AuthResult>("/auth/login",{email,password})).data;
    if(generation!==authGeneration)throw sessionEnded();
    setAuth(data);return data.user;
  });
}
export function refreshSession():Promise<AuthResult>{
  if(!refreshPromise){
    const generation=authGeneration;
    const pending=authRequest(async()=>{
      if(generation!==authGeneration)throw sessionEnded();
      const data=(await authApi.post<AuthResult>("/auth/refresh")).data;
      if(generation!==authGeneration)throw sessionEnded();
      setAuth(data);return data;
    }).catch(error=>{
      if(generation===authGeneration){
        setAuth(null);
        if(error.response?.data?.detail==='Your session expired due to inactivity.')
          sessionStorage.setItem('annotation-idle-message',error.response.data.detail);
      }
      throw error;
    }).finally(()=>{if(refreshPromise===pending)refreshPromise=null;});
    refreshPromise=pending;
  }
  return refreshPromise;
}
type SessionRequest=InternalAxiosRequestConfig & {_authGeneration?:number;_authRetried?:boolean};
api.interceptors.request.use((config:SessionRequest)=>{
  if(config._authGeneration!==undefined&&config._authGeneration!==authGeneration)throw sessionEnded();
  config._authGeneration=authGeneration;
  if(accessToken)config.headers.set('Authorization', 'Bearer '+accessToken);
  else config.headers.delete('Authorization');
  return config;
});
api.interceptors.response.use(response=>{
  if((response.config as SessionRequest)._authGeneration!==authGeneration)throw sessionEnded();
  return response;
},async error=>{
  const config=error.config as SessionRequest|undefined;
  if(config?._authGeneration!==undefined&&config._authGeneration!==authGeneration)return Promise.reject(sessionEnded());
  if(error.response?.status===401&&error.response?.data?.detail==='Your session expired due to inactivity.'){
    sessionStorage.setItem('annotation-idle-message',error.response.data.detail);
    window.dispatchEvent(new Event('session-idle-expired'));setAuth(null);return Promise.reject(error);
  }
  if(typeof window!=="undefined"&&[403,404].includes(error.response?.status)&&/\/(projects|images|annotations|predictions|storage)\//.test(config?.url??""))window.dispatchEvent(new Event("workspace-access-denied"));
  if(error.response?.status!==401||!config)return Promise.reject(error);
  if(config._authRetried){setAuth(null);return Promise.reject(error);}
  config._authRetried=true;
  try{await refreshSession();return api.request(config);}catch{return Promise.reject(error);}
});
export function signOut(all=false):Promise<void>{
  if(logoutPromise)return logoutPromise;
  const token=accessToken,id=sessionPolicy?.id,userId=currentUser?.id;
  window.dispatchEvent(new Event('session-logout'));
  setAuth(null);
  const pending=authRequest(async()=>{
    try{
      await authApi.post(all?"/auth/logout-all":"/auth/logout",
        !all&&id?{session_id:id}:undefined,
        {headers:token?{Authorization:'Bearer '+token}:{},timeout:10000});
    }catch(error){
      if(!all||!axios.isAxiosError(error)||error.response?.status!==401)throw error;
      const data=(await authApi.post<AuthResult>('/auth/refresh',undefined,{timeout:10000})).data;
      if(data.user.id!==userId||(id&&data.session?.id!==id))throw sessionEnded();
      await authApi.post('/auth/logout-all',undefined,{headers:{Authorization:'Bearer '+data.access_token},timeout:10000});
    }
  }).finally(()=>{if(logoutPromise===pending)logoutPromise=null;});
  logoutPromise=pending;
  return pending;
}
export function revokeSession(id:string):Promise<unknown>{
  return authRequest(()=>authApi.post('/auth/logout',{session_id:id},{timeout:10000}));
}
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
