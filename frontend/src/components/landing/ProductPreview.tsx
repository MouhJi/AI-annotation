import {useEffect,useId,useRef,useState} from 'react';

import LandingIcon from './LandingIcon';

type DemoObject = {id:string;label:string;author:string;color:string;box:[number,number,number,number];polygon:string};
const objects:DemoObject[]=[
  {id:'car',label:'Car',author:'Nguyễn An',color:'#60a5fa',box:[241,221,226,111],polygon:'244,302 258,264 299,255 323,226 391,226 421,256 455,266 465,304 451,325 260,325'},
  {id:'person',label:'Person',author:'Trần Bình',color:'#fbbf24',box:[520,169,51,143],polygon:'541,172 556,174 561,192 557,205 568,235 564,255 558,245 558,273 568,308 552,309 544,278 539,309 525,309 533,269 530,237 525,255 519,249 530,212 537,204 532,190'},
  {id:'tree',label:'Tree',author:'Nguyễn An',color:'#5eead4',box:[82,65,98,202],polygon:'128,68 151,88 157,115 178,137 170,163 149,176 146,262 126,265 123,176 95,172 83,149 97,124 98,97'}
];

function StreetScene(){
  return <g aria-hidden="true">
    <rect width="720" height="390" fill="#dcebf1"/>
    <rect y="164" width="720" height="100" fill="#d4d5cc"/>
    <path d="M0 0H218V230H0Z" fill="#e6d6c1"/><path d="M218 0H431V230H218Z" fill="#f2e6d6"/><path d="M431 0H720V230H431Z" fill="#b4c9ca"/>
    <path d="M0 26H218M0 118H218M218 64H431M431 59H720M431 151H720" stroke="#c5b7a5" strokeWidth="5"/>
    {[26,92,158,248,311,374,460,526,592,658].map((x,i)=><g key={x}><rect x={x} y={i<3?46:86} width="35" height="51" rx="2" fill="#60777c"/><path d={`M${x+17} ${i<3?46:86}v51`} stroke="#d5d6ca" strokeWidth="3"/></g>)}
    <rect x="240" y="160" width="165" height="70" fill="#537372"/><rect x="235" y="153" width="175" height="15" fill="#73938a"/>
    <text x="322" y="164" textAnchor="middle" fill="#fff9e9" fontSize="8" letterSpacing="3">CORNER STORE</text>
    <rect x="291" y="176" width="41" height="54" fill="#a9bdb2"/>
    <rect x="601" y="163" width="89" height="67" fill="#6e8687"/>
    <path d="M0 231H720V273H0Z" fill="#c5c6bf"/><path d="M0 271H720V390H0Z" fill="#64747d"/><path d="M0 275H720" stroke="#ecede5" strokeWidth="5"/>
    <path d="M20 365H118M194 365H292M368 365H466M542 365H640" stroke="#cdd7d5" strokeWidth="4"/>
    <ellipse cx="353" cy="328" rx="126" ry="12" fill="#364954" opacity=".35"/>
    <path d="M244 299L259 266 302 256 324 229H390L422 258 451 268 465 301V316H244Z" fill="#408ac4"/>
    <path d="M309 255L329 234H357V255ZM364 234H387L409 255H364Z" fill="#c7e0e9"/><path d="M255 277H451M360 261V310" stroke="#2d6ca2" strokeWidth="2"/>
    <rect x="372" y="265" width="13" height="4" rx="2" fill="#c9e2e9"/>
    <circle cx="283" cy="311" r="19" fill="#304351"/><circle cx="283" cy="311" r="10" fill="#a3b6be"/><circle cx="429" cy="311" r="19" fill="#304351"/><circle cx="429" cy="311" r="10" fill="#a3b6be"/>
    <path d="M244 292H258M449 283H461" stroke="#f6e7ba" strokeWidth="7"/>
    <rect x="126" y="151" width="15" height="112" fill="#89795c"/>
    <circle cx="127" cy="111" r="40" fill="#718d71"/><circle cx="109" cy="143" r="31" fill="#668669"/><circle cx="148" cy="141" r="30" fill="#809d75"/>
    <ellipse cx="544" cy="313" rx="26" ry="5" fill="#50616a" opacity=".35"/>
    <circle cx="545" cy="189" r="14" fill="#b98565"/><path d="M531 187Q534 168 549 175Q561 174 559 189" fill="#3c4241"/>
    <path d="M535 207L552 206 562 245 553 264H534L529 239Z" fill="#d18d58"/><path d="M534 214L523 249M553 215L564 247" stroke="#bc845e" strokeWidth="10" strokeLinecap="round"/>
    <path d="M538 259L535 300M549 259L558 300" stroke="#334a60" strokeWidth="12"/><path d="M526 307H540M552 307H566" stroke="#e8e2cf" strokeWidth="7" strokeLinecap="round"/>
    <path d="M0 0V390H720V0Z" fill="#12344b" opacity=".06"/>
  </g>;
}

export default function ProductPreview({initialMode='bbox',compact=false,ai=false}:{initialMode?:'bbox'|'polygon';compact?:boolean;ai?:boolean}){
  const [mode,setMode]=useState(initialMode),[selected,setSelected]=useState('car');
  const [playing,setPlaying]=useState(false),[reduced,setReduced]=useState(false);
  const [visible,setVisible]=useState(false),[foreground,setForeground]=useState(document.visibilityState!=='hidden');
  const surface=useRef<HTMLDivElement>(null),id=useId();
  useEffect(()=>{
    const media=window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const preference=()=>{const reduce=!!media?.matches;setReduced(reduce);if(reduce)setPlaying(false);};
    preference();if(!media?.matches)setPlaying(true);
    media?.addEventListener?.('change',preference);
    const observer=typeof IntersectionObserver==='undefined'?undefined:new IntersectionObserver(entries=>{
      setVisible(entries.some(entry=>entry.isIntersecting));
    },{threshold:.2});
    if(observer)observer.observe(surface.current!);else setVisible(true);
    const visibility=()=>setForeground(document.visibilityState!=='hidden');
    document.addEventListener('visibilitychange',visibility);
    return()=>{observer?.disconnect();media?.removeEventListener?.('change',preference);document.removeEventListener('visibilitychange',visibility);};
  },[]);
  useEffect(()=>{
    if(!playing||reduced||!visible||!foreground)return;
    const timer=window.setInterval(()=>setSelected(current=>{
      const index=objects.findIndex(object=>object.id===current);
      return objects[(index+1)%objects.length].id;
    }),3200);
    return()=>window.clearInterval(timer);
  },[playing,reduced,visible,foreground]);
  const choose=(objectId:string)=>{setPlaying(false);setSelected(objectId);};
  const changeMode=(value:'bbox'|'polygon')=>{setPlaying(false);setMode(value);};
  const current=objects.find(object=>object.id===selected)!;
  return <div ref={surface} className={'lp-preview'+(compact?' lp-preview-compact':'')} data-playing={playing&&!reduced} data-motion={reduced?'reduced':'full'}>
    <div className="lp-preview-bar"><span className="lp-preview-location"><img src="/favicon.svg" width="24" height="24" alt=""/><b>AnnotateAI</b><span aria-hidden="true">/</span><span>street_001.svg</span></span><span className="lp-demo-tag">Interactive preview</span><button type="button" className="lp-preview-motion" disabled={reduced} aria-label={reduced?'Preview uses reduced motion':playing?'Pause preview':'Play preview'} onClick={()=>setPlaying(value=>!value)}><LandingIcon name={playing&&!reduced?'pause':'play'}/><span>{reduced?'Reduced motion':playing?'Pause':'Play preview'}</span></button></div>
    <div className="lp-preview-toolbar"><span className="lp-editor-label"><span className="lp-status-dot"/>Annotation editor</span><div className="lp-mode-switch" role="group" aria-label="Sample annotation type"><button type="button" aria-pressed={mode==='bbox'} onClick={()=>changeMode('bbox')}><LandingIcon name="bounding-box"/>Bounding box</button><button type="button" aria-pressed={mode==='polygon'} onClick={()=>changeMode('polygon')}><LandingIcon name="polygon"/>Polygon</button></div><span className="lp-preview-class"><LandingIcon name="sparkle"/>YOLO + manual review</span></div>
    <div className="lp-preview-body"><div className="lp-toolrail" aria-hidden="true"><span className="lp-tool-active"><LandingIcon name="cursor"/></span><span><LandingIcon name="bounding-box"/></span><span><LandingIcon name="polygon"/></span><span><LandingIcon name="sparkle"/></span></div>
      <div className="lp-demo-canvas"><svg viewBox="0 0 720 390" role="group" aria-labelledby={id+'-scene-title'}><title id={id+'-scene-title'}>Sample street scene with a car, a person and a tree. Select an object to view its bounding box or polygon.</title><StreetScene/>{objects.map((object,index)=>{
        const [x,y,w,h]=object.box,active=object.id===selected;
        return <g key={object.id} className="lp-demo-object" data-index={index} data-selected={active} style={{color:object.color}}><title>{object.label+' · '+object.author+' (sample data)'}</title>
          <g className="lp-demo-geometry" key={mode}>{mode==='bbox'?<rect x={x} y={y} width={w} height={h} fill="currentColor" fillOpacity={active ? 0.12 : 0.03} stroke="currentColor" strokeWidth={active?2.5:1.5} strokeDasharray={ai?'6 4':undefined}/>:<polygon points={object.polygon} fill="currentColor" fillOpacity={active ? 0.28 : 0.12} stroke="currentColor" strokeWidth={active?2.5:1.5}/>}
            <rect x={x} y={y-24} width={object.id==='person'?168:128} height="24" rx="4" fill="currentColor"/><text x={x+8} y={y-8} fill="#102337" fontSize="12" fontWeight="600">{object.label+' · '+(active?'Selected':'Sample label')}</text>
            {active&&mode==='bbox'&&[[x,y],[x+w,y],[x,y+h],[x+w,y+h]].map(([cx,cy],i)=><rect key={i} x={cx-3} y={cy-3} width="6" height="6" fill="white" stroke="currentColor"/>)}
          </g>
          <rect x={x} y={y-24} width={w} height={h+24} fill="transparent" role="button" aria-label={'Select sample '+object.label} aria-pressed={active} tabIndex={0} onClick={()=>choose(object.id)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(object.id);}}}/>
        </g>;
      })}</svg><div className="lp-canvas-caption"><span>{mode==='bbox'?'Bounding box':'Instance segmentation'}</span><span>Select an object to view its label</span></div></div>
      <aside className="lp-object-panel" aria-label="Sample objects"><div className="lp-object-heading"><b>Objects</b><span>{objects.length}</span></div>{objects.map(object=><button key={object.id} type="button" aria-pressed={selected===object.id} onClick={()=>choose(object.id)}><span className={'lp-object-dot lp-dot-'+object.id}/><span><b>{object.label}</b><small>{object.author}</small></span>{selected===object.id&&<LandingIcon name="check"/>}</button>)}
        <div className="lp-demo-details" key={selected}><span>Viewing</span><b>{current.label}</b><span>Sample label creator</span><b>{current.author}</b><span>Label type</span><b>{mode==='bbox'?'Bounding box':'Polygon'}</b></div>
        <p>Image and annotator names are sample data.</p>
      </aside>
    </div>
    <div className="lp-preview-footer"><span><LandingIcon name="check"/>Select an object or switch annotation types to explore</span><span>Local preview. No AI inference runs here.</span></div>
  </div>;
}
