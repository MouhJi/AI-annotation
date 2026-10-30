import type {ReviewState} from '../types';
import './Quality.css';
export const stateLabels:Record<ReviewState,string>={not_started:'Not started',in_progress:'In progress',pending_review:'Pending review',changes_requested:'Changes requested',approved:'Approved'};
export const errorLabels:Record<string,string>={wrong_class:'Wrong class',missing_object:'Missing object',extra_object:'Extra object',inaccurate_bbox:'Inaccurate bounding box',inaccurate_polygon:'Inaccurate polygon',other:'Other'};
export const errorMessage=(error:any,fallback:string)=>{const detail=error.response?.data?.detail;return typeof detail==='string'?detail:fallback;};
export function ReviewBadge({state='not_started'}:{state?:ReviewState}){return <span className={'badge review-badge review-'+state}>{stateLabels[state]}</span>;}
export function StateOptions(){return <>{Object.entries(stateLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</>;}
export function SplitOptions(){return <><option value="">All dataset splits</option><option value="train">Train</option><option value="val">Validation</option><option value="test">Test</option><option value="unassigned">Unassigned</option></>;}
