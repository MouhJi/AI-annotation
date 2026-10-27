// @vitest-environment jsdom
import {afterEach,describe,it,expect,vi} from "vitest";
import {AxiosError,AxiosHeaders,type AxiosResponse,type InternalAxiosRequestConfig} from "axios";
import {api,authApi,refreshSession,setAuth,subscribeAuth,signOut,loginSession,updateAuthUser} from "./api";
const user={id:"uuid",email:"user@example.com",full_name:"User",status:"active",email_verified:true,created_at:"2026-01-01"};
const response=(config:InternalAxiosRequestConfig,data:unknown):AxiosResponse=>({config,data,status:200,statusText:"OK",headers:{}});
const originalApi=api.defaults.adapter,originalAuth=authApi.defaults.adapter;
afterEach(()=>{api.defaults.adapter=originalApi;authApi.defaults.adapter=originalAuth;setAuth(null);vi.restoreAllMocks()});
describe("memory authentication client",()=>{
 it("restores a session without storing tokens in localStorage",async()=>{const spy=vi.spyOn(Storage.prototype,"setItem");authApi.defaults.adapter=async config=>response(config,{access_token:"new",user});const listener=vi.fn();const unsubscribe=subscribeAuth(listener);await refreshSession();expect(listener).toHaveBeenLastCalledWith(user);expect(spy).not.toHaveBeenCalled();unsubscribe()});
 it("shares a single refresh among concurrent requests",async()=>{setAuth({access_token:"expired",user});let refreshes=0;authApi.defaults.adapter=async config=>{refreshes++;await new Promise(resolve=>setTimeout(resolve,20));return response(config,{access_token:"fresh",user})};api.defaults.adapter=async config=>{if(config.headers.Authorization==="Bearer fresh")return response(config,{ok:true});throw new AxiosError("Expired","401",config,undefined,{...response(config,{}),status:401})};const results=await Promise.all([api.get("/projects"),api.get("/users/me"),api.get("/auth/sessions")]);expect(refreshes).toBe(1);expect(results.every(result=>result.data.ok)).toBe(true)});
 it("never loops when a retried request remains unauthorized",async()=>{let refreshes=0,requests=0;authApi.defaults.adapter=async config=>{refreshes++;return response(config,{access_token:"bad",user})};api.defaults.adapter=async config=>{requests++;throw new AxiosError("Unauthorized","401",config,undefined,{...response(config,{}),status:401})};await expect(api.get("/projects")).rejects.toThrow();expect(refreshes).toBe(1);expect(requests).toBe(2)});
 it("clears authentication if cookie restoration fails",async()=>{setAuth({access_token:"old",user});const listener=vi.fn();const stop=subscribeAuth(listener);authApi.defaults.adapter=async config=>{throw new AxiosError("Expired","401",config)};await expect(refreshSession()).rejects.toThrow();expect(listener).toHaveBeenLastCalledWith(null);stop()});
 it("revokes session and clears memory on logout",async()=>{setAuth({access_token:"token",user});const listener=vi.fn();const stop=subscribeAuth(listener);authApi.defaults.adapter=async config=>response(config,{});await signOut();expect(listener).toHaveBeenLastCalledWith(null);stop()});
 it("does not refresh forbidden responses",async()=>{const refresh=vi.fn();authApi.defaults.adapter=refresh;api.defaults.adapter=async config=>{throw new AxiosError("Forbidden","403",config,undefined,{...response(config,{}),status:403})};await expect(api.get("/projects")).rejects.toThrow();expect(refresh).not.toHaveBeenCalled()});
});

const other={...user,id:'other-user',email:'other@example.com',is_platform_admin:false};
function deferred<T>(){let resolve!:(value:T)=>void,reject!:(error:unknown)=>void;const promise=new Promise<T>((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};}
it('clears local state immediately, revokes the captured session and queues login behind logout',async()=>{
  const policy={id:'old-session',server_time:'',idle_expires_at:'',idle_timeout_seconds:3600,warning_seconds:300};
  setAuth({access_token:'old-admin',user:{...user,is_platform_admin:true},session:policy});
  localStorage.setItem('workspace:'+user.id,'private-workspace');localStorage.setItem('returnTo','/admin');sessionStorage.setItem('redirectTo','/admin/users');
  const pending=deferred<AxiosResponse>(),started=deferred<void>(),calls:string[]=[];
  authApi.defaults.adapter=async config=>{
    calls.push(config.url!);
    if(config.url==='/auth/logout'){expect(JSON.parse(config.data)).toEqual({session_id:'old-session'});started.resolve();await pending.promise;return response(config,{});}
    return response(config,{access_token:'new-user',user:other});
  };
  const listener=vi.fn(),stop=subscribeAuth(listener),ending=signOut();
  expect(listener).toHaveBeenLastCalledWith(null);expect(localStorage.getItem('workspace:'+user.id)).toBeNull();expect(localStorage.getItem('returnTo')).toBeNull();expect(sessionStorage.getItem('redirectTo')).toBeNull();
  await started.promise;
  const signingIn=loginSession(other.email,'test password');
  expect(calls).toEqual(['/auth/logout']);
  pending.resolve({} as AxiosResponse);await ending;await signingIn;
  expect(calls).toEqual(['/auth/logout','/auth/login']);expect(listener).toHaveBeenLastCalledWith(other);stop();
});
it('discards an old successful response before it can populate the next account cache',async()=>{
  setAuth({access_token:'old',user});
  const pending=deferred<void>(),started=deferred<void>();
  api.defaults.adapter=async config=>{started.resolve();await pending.promise;return response(config,{secret:'old private data'});};
  const cache=vi.fn(),request=api.get('/projects').then(cache),rejected=expect(request).rejects.toThrow(/session changed/);
  await started.promise;setAuth(null);setAuth({access_token:'new',user:other});pending.resolve();await rejected;expect(cache).not.toHaveBeenCalled();
});
for(const status of [401,403,404])it(`ignores old ${status} errors without clearing the new session or firing access events`,async()=>{
  setAuth({access_token:'old',user});const pending=deferred<void>(),started=deferred<void>();
  api.defaults.adapter=async config=>{started.resolve();await pending.promise;throw new AxiosError('Old error',String(status),config,undefined,{...response(config,{}),status,data:{detail:'Your session expired due to inactivity.'}});};
  const expired=vi.fn(),denied=vi.fn(),listener=vi.fn(),stop=subscribeAuth(listener);
  window.addEventListener('session-idle-expired',expired);window.addEventListener('workspace-access-denied',denied);
  try{
    const rejected=expect(api.get('/projects/1')).rejects.toThrow(/session changed/);await started.promise;
    setAuth(null);setAuth({access_token:'new',user:other});pending.resolve();await rejected;
    expect(listener).toHaveBeenLastCalledWith(other);expect(expired).not.toHaveBeenCalled();expect(denied).not.toHaveBeenCalled();
  }finally{stop();window.removeEventListener('session-idle-expired',expired);window.removeEventListener('workspace-access-denied',denied);}
});
for(const succeeds of [true,false])it(`does not let a stale refresh ${succeeds?'success':'failure'} overwrite a subsequent login`,async()=>{
  setAuth({access_token:'old',user});const pending=deferred<void>(),started=deferred<void>(),calls:string[]=[];
  authApi.defaults.adapter=async config=>{
    calls.push(config.url!);
    if(config.url==='/auth/refresh'){started.resolve();await pending.promise;if(!succeeds)throw new AxiosError('Expired','401',config);return response(config,{access_token:'stale',user});}
    return response(config,{access_token:'new',user:other});
  };
  const refresh=expect(refreshSession()).rejects.toThrow(),listener=vi.fn(),stop=subscribeAuth(listener);
  await started.promise;const login=loginSession(other.email,'test password');pending.resolve();await refresh;await login;
  expect(calls).toEqual(['/auth/refresh','/auth/login']);expect(listener).toHaveBeenLastCalledWith(other);stop();
});
it('cannot restore an old profile after logout or switch identities using updateAuthUser',()=>{
  setAuth({access_token:'old',user});setAuth(null);const listener=vi.fn(),stop=subscribeAuth(listener);
  updateAuthUser(user);expect(listener).toHaveBeenLastCalledWith(null);
  setAuth({access_token:'new',user:other});updateAuthUser({...user,is_platform_admin:true});expect(listener).toHaveBeenLastCalledWith(other);stop();
});
it('keeps the client signed out if server revocation fails',async()=>{
  setAuth({access_token:'old',user});authApi.defaults.adapter=async()=>{throw new Error('offline');};
  const listener=vi.fn(),stop=subscribeAuth(listener);await expect(signOut()).rejects.toThrow('offline');expect(listener).toHaveBeenLastCalledWith(null);stop();
});
it('refreshes an expired access token only for logout-all without restoring the client session',async()=>{
  setAuth({access_token:'expired',user});const calls:string[]=[],listener=vi.fn(),stop=subscribeAuth(listener);
  authApi.defaults.adapter=async config=>{
    calls.push(config.url!);
    if(config.url==='/auth/refresh')return response(config,{access_token:'fresh',user});
    if(config.headers.Authorization==='Bearer expired')throw new AxiosError('Expired','401',config,undefined,{...response(config,{}),status:401});
    expect(config.headers.Authorization).toBe('Bearer fresh');return response(config,{});
  };
  await signOut(true);expect(calls).toEqual(['/auth/logout-all','/auth/refresh','/auth/logout-all']);expect(listener).toHaveBeenLastCalledWith(null);stop();
});
