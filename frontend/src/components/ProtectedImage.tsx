import {useEffect,useState,type ImgHTMLAttributes} from "react";
import {api} from "../services/api";
export default function ProtectedImage({src,onError,...props}:ImgHTMLAttributes<HTMLImageElement>){
 const [blob,setBlob]=useState("");const [failed,setFailed]=useState(false);
 useEffect(()=>{let alive=true;let url="";setBlob("");setFailed(false);if(src)void api.get(src,{responseType:"blob"}).then(response=>{if(alive){url=URL.createObjectURL(response.data);setBlob(url)}}).catch(()=>{if(alive)setFailed(true)});return()=>{alive=false;if(url)URL.revokeObjectURL(url)}},[src]);
 return blob?<img {...props} src={blob} onError={onError}/>:failed?<span role="img" aria-label="Unable to load image">Unable to load image</span>:null;
}
