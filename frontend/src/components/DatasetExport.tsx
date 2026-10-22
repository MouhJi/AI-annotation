import {useEffect,useState} from "react";
import {api} from "../services/api";
import type {SplitSummary} from "../types";

type Props={projectId:string};
const initial={train:80,val:10,test:10};

export default function DatasetExport({projectId}:Props){
 const [ratios,setRatios]=useState(initial); const [summary,setSummary]=useState<SplitSummary>(); const [busy,setBusy]=useState(false); const [message,setMessage]=useState(""); const [error,setError]=useState("");
 const readSummary=async()=>{try{setSummary((await api.get(`/projects/${projectId}/dataset/split`)).data)}catch(e:any){setError(e.response?.data?.detail??"Unable to load split status")}};
 useEffect(()=>{void readSummary()},[projectId]);
 const configure=async()=>{setError("");setMessage("");if(Object.values(ratios).reduce((a,b)=>a+b,0)!==100){setError("Train, validation, and test must total 100%.");return}try{setBusy(true);setSummary((await api.put(`/projects/${projectId}/dataset/split`,ratios)).data);setMessage("Split saved. Future exports will keep these assignments.")}catch(e:any){setError(e.response?.data?.detail??"Unable to save split")}finally{setBusy(false)}};
 const exportYolo=async()=>{setError("");setMessage("");try{setBusy(true);const response=await api.post(`/projects/${projectId}/dataset/export/yolo`,{}, {responseType:"blob"});const url=URL.createObjectURL(response.data);const link=document.createElement("a");link.href=url;link.download="dataset-yolo.zip";link.click();URL.revokeObjectURL(url);setMessage("YOLO ZIP created and download started.")}catch(e:any){setError(e.response?.data?.detail??"Unable to export YOLO dataset")}finally{setBusy(false)}};
 return <section className="dataset-export"><h2>Dataset Export</h2><p>Configure the persistent image split, then download a YOLO-compatible ZIP.</p><div className="split-inputs">{(["train","val","test"] as const).map(key=><label key={key}>{key === "val" ? "Validation" : key[0].toUpperCase()+key.slice(1)}<input type="number" min="0" max="100" value={ratios[key]} onChange={e=>setRatios({...ratios,[key]:Number(e.target.value)})}/>%</label>)}</div><div className="export-actions"><button disabled={busy} onClick={configure}>{busy?"Working…":"Save split"}</button><button disabled={busy} onClick={exportYolo}>Export YOLO</button></div>{summary&&<p className="split-summary">Assigned: {summary.train} train · {summary.val} validation · {summary.test} test ({summary.total} total){!summary.configured&&" — not configured yet"}</p>}{message&&<p className="success">{message}</p>}{error&&<p className="error">{error}</p>}</section>
}
