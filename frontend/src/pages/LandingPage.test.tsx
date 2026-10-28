// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest';
import {act,cleanup,render,screen,fireEvent,within} from '@testing-library/react';
import {MemoryRouter,Route,Routes} from 'react-router-dom';
import LandingPage from './LandingPage';
const auth=vi.hoisted(()=>({user:null as null|{id:string},initializing:false}));
vi.mock('../auth/AuthProvider',()=>({useAuth:()=>auth}));
afterEach(()=>{cleanup();auth.user=null;auth.initializing=false;vi.unstubAllGlobals();});
const show=()=>render(<MemoryRouter><LandingPage/></MemoryRouter>);

it('renders English product sections, a real editor image and valid section links',()=>{
  const {container}=show();
  expect(screen.getByRole('heading',{level:1}).textContent).toBe('Better training data.One label at a time.');
  expect(screen.getAllByRole('link',{name:'Start annotating'}).every(link=>link.getAttribute('href')==='/register')).toBe(true);
  const nav=screen.getByRole('navigation',{name:'Main navigation'});
  expect(within(nav).getByRole('link',{name:'Features'}).getAttribute('href')).toBe('#chuc-nang');
  for(const anchor of container.querySelectorAll('a')){
    const href=anchor.getAttribute('href')!;
    expect(href).not.toBe('#');
    if(href.startsWith('#'))expect(container.querySelector(href)).toBeTruthy();
  }
  expect(container.querySelectorAll('.lp-feature-card')).toHaveLength(4);
  expect(container.querySelectorAll('.lp-steps li')).toHaveLength(3);
  expect(container.querySelectorAll('.lp-faq-list details')).toHaveLength(8);
  expect(screen.getByAltText(/AnnotateAI editor/).getAttribute('src')).toBe('/landing/annotation-editor.png');
  expect(screen.getByText('The actual editor with sample data in Viewer mode.')).toBeTruthy();
  expect(screen.getByRole('group',{name:'Sample annotation type'})).toBeTruthy();
  expect(screen.getByText('Local preview. No AI inference runs here.')).toBeTruthy();
  expect(container.textContent).not.toMatch(/free trial|trusted by|5.star|faster than/);
  expect(document.title).toContain('Image annotation');
  const schema=JSON.parse(container.querySelector('script[type="application/ld+json"]')!.textContent!);
  expect(schema.mainEntity).toHaveLength(8);
});
it('preserves the authenticated workspace destination without redirecting or changing platform routing',()=>{
  auth.user={id:'current-user'};show();
  expect(screen.getAllByRole('link',{name:'Start annotating'}).every(link=>link.getAttribute('href')==='/projects')).toBe(true);
  expect(screen.getByRole('heading',{level:1})).toBeTruthy();
});
for(const signedIn of [false,true])it('navigates its main CTA to '+(signedIn?'/projects':'/register'),()=>{
  if(signedIn)auth.user={id:'user'};
  render(<MemoryRouter><Routes><Route path="/" element={<LandingPage/>}/><Route path="/projects" element={<p>Existing workspace route</p>}/><Route path="/register" element={<p>Existing registration route</p>}/></Routes></MemoryRouter>);
  fireEvent.click(within(screen.getByRole('main')).getAllByRole('link',{name:'Start annotating'})[0]);
  expect(screen.getByText(signedIn?'Existing workspace route':'Existing registration route')).toBeTruthy();
});
it('opens a full mobile menu, traps focus, follows section links and restores focus on Escape',()=>{
  const initialOverflow=document.body.style.overflow;show();
  const toggle=screen.getByRole('button',{name:'Open menu'});fireEvent.click(toggle);
  const dialog=screen.getByRole('dialog',{name:'Navigation menu'});
  const mobile=within(dialog).getByRole('navigation',{name:'Mobile navigation'});
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  expect(document.body.style.overflow).toBe('hidden');
  expect(document.activeElement).toBe(within(mobile).getByRole('link',{name:'Features'}));
  const last=within(mobile).getByRole('link',{name:'Start annotating'});
  last.focus();fireEvent.keyDown(dialog,{key:'Tab'});
  expect(document.activeElement).toBe(within(dialog).getByRole('link',{name:'AnnotateAI, home'}));
  fireEvent.click(within(mobile).getByRole('link',{name:'Collaboration'}));
  expect(screen.queryByRole('dialog')).toBeNull();expect(document.body.style.overflow).toBe(initialOverflow);
  fireEvent.click(toggle);fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'});
  expect(toggle.getAttribute('aria-expanded')).toBe('false');expect(document.activeElement).toBe(toggle);
});
it('has actual privacy/usage disclosures rather than placeholder footer links',()=>{
  const {container}=show();
  fireEvent.click(screen.getByRole('link',{name:'Privacy'}));
  expect((container.querySelector('#quyen-rieng-tu') as HTMLDetailsElement).open).toBe(true);
  fireEvent.click(screen.getByRole('link',{name:'Terms of use'}));
  expect((container.querySelector('#dieu-kien-su-dung') as HTMLDetailsElement).open).toBe(true);
  expect(screen.getByText(/retention, backup/)).toBeTruthy();
});
it('unlocks page scrolling when resizing an open mobile menu to desktop',()=>{
  let changed!:()=>void;
  const wide={matches:false,addEventListener:vi.fn((_:string,callback:()=>void)=>{changed=callback;}),removeEventListener:vi.fn()};
  vi.stubGlobal('matchMedia',(query:string)=>query.includes('min-width')?wide:{matches:false});
  const initialOverflow=document.body.style.overflow;show();
  fireEvent.click(screen.getByRole('button',{name:'Open menu'}));expect(document.body.style.overflow).toBe('hidden');
  act(()=>{wide.matches=true;changed();});
  expect(screen.queryByRole('dialog')).toBeNull();expect(document.body.style.overflow).toBe(initialOverflow);
});
it('shows a screenshot skeleton, then the loaded image or a useful inline error',()=>{
  const {container}=show();const image=screen.getByAltText(/AnnotateAI editor/);
  expect(screen.getByText('Loading editor screenshot…')).toBeTruthy();
  fireEvent.load(image);expect(screen.queryByText('Loading editor screenshot…')).toBeNull();
  expect(image.classList.contains('is-loaded')).toBe(true);
  expect(container.querySelector('.lp-shot-body')?.getAttribute('aria-busy')).toBe('false');
  fireEvent.error(image);expect(screen.getByText('Could not load the editor screenshot')).toBeTruthy();
  expect(screen.getByRole('link',{name:'Explore the features'}).getAttribute('href')).toBe('#chuc-nang');
});
it('restores document language/title and body scrolling when leaving the landing',()=>{
  const title=document.title,lang=document.documentElement.lang,overflow=document.body.style.overflow;
  const result=show();expect(document.documentElement.lang).toBe('en');
  fireEvent.click(screen.getByRole('button',{name:'Open menu'}));result.unmount();
  expect(document.title).toBe(title);expect(document.documentElement.lang).toBe(lang);expect(document.body.style.overflow).toBe(overflow);
});
function observerMock(){
  const observers:{callback:(entries:Partial<IntersectionObserverEntry>[])=>void;observe:ReturnType<typeof vi.fn>;unobserve:ReturnType<typeof vi.fn>;disconnect:ReturnType<typeof vi.fn>}[]=[];
  vi.stubGlobal('IntersectionObserver',class {
    observe=vi.fn();unobserve=vi.fn();disconnect=vi.fn();
    constructor(public callback:(entries:Partial<IntersectionObserverEntry>[])=>void){observers.push(this);}
  });
  return observers;
}
it('reveals sections once, activates tagline words individually and indicates the visible nav section',()=>{
  const observers=observerMock(),result=show();
  const section=result.container.querySelector('#quy-trinh')!,reveal=result.container.querySelector('[data-reveal]')!,words=result.container.querySelectorAll('[data-word]');
  const observing=(target:Element)=>observers.find(observer=>observer.observe.mock.calls.some(([node])=>node===target))!;
  const sectionObserver=observing(section),revealObserver=observing(reveal),wordObserver=observing(words[0]);
  act(()=>sectionObserver.callback([{isIntersecting:true,target:section}]));
  expect(within(screen.getByRole('navigation',{name:'Main navigation'})).getByRole('link',{name:'Workflow'}).getAttribute('aria-current')).toBe('location');
  act(()=>revealObserver.callback([{isIntersecting:true,target:reveal}]));
  expect(reveal.classList.contains('is-visible')).toBe(true);expect(revealObserver.unobserve).toHaveBeenCalledWith(reveal);
  act(()=>wordObserver.callback([{isIntersecting:true,target:words[0]}]));
  expect(words[0].classList.contains('is-active')).toBe(true);expect(words[1].classList.contains('is-active')).toBe(false);
  result.unmount();for(const observer of observers)expect(observer.disconnect).toHaveBeenCalled();
});
it('keeps content visible without motion for reduced-motion preference',()=>{
  const observers=observerMock();vi.stubGlobal('matchMedia',()=>({matches:true}));
  const {container}=show();expect(container.querySelector('.lp-root')?.getAttribute('data-motion')).toBeNull();expect(observers).toHaveLength(2);
  expect((screen.getByRole('button',{name:'Preview uses reduced motion'}) as HTMLButtonElement).disabled).toBe(true);
});
it('allows keyboard exploration of workspace roles without changing actual permissions',()=>{
  show();const viewer=screen.getByRole('tab',{name:'Viewer'});fireEvent.click(viewer);
  expect(screen.getByRole('tabpanel').textContent).toContain('Cannot create, edit or delete labels');
  fireEvent.keyDown(viewer,{key:'Home'});expect(screen.getByRole('tab',{name:'Owner'}).getAttribute('aria-selected')).toBe('true');
  expect(document.activeElement).toBe(screen.getByRole('tab',{name:'Owner'}));
});
