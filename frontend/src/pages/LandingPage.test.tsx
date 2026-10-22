// @vitest-environment jsdom
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,render,screen,fireEvent,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import LandingPage from './LandingPage';
const auth=vi.hoisted(()=>({user:null as null|{id:string},initializing:false}));
vi.mock('../auth/AuthProvider',()=>({useAuth:()=>auth}));
afterEach(()=>{cleanup();auth.user=null});
const show=()=>render(<MemoryRouter><LandingPage/></MemoryRouter>);
it('renders public sections with working guest destinations and no fake links',()=>{
 const {container}=show();
 expect(screen.getByRole('heading',{level:1}).textContent).toBe('Build Better AIwith Better Data.');
 expect(screen.getByRole('link',{name:'Start Annotating'}).getAttribute('href')).toBe('/register');
 const nav=screen.getByRole('navigation',{name:'Main navigation'});
 expect(within(nav).getByRole('link',{name:'Features'}).getAttribute('href')).toBe('#features');
 for(const anchor of container.querySelectorAll('a')){const href=anchor.getAttribute('href')!;expect(href).not.toBe('#');if(href.startsWith('#'))expect(container.querySelector(href)).toBeTruthy()}
 expect(container.querySelectorAll('.lp-feature-card').length).toBe(6);
 expect(screen.queryByText('Documentation')).toBeNull();expect(screen.queryByText(/Get Started for Free/)).toBeNull();
 expect(document.title).toContain('Build Better AI');
});
it('sends authenticated users to the existing dashboard without redirecting the landing page',()=>{
 auth.user={id:'demo-id'};show();expect(screen.getByRole('link',{name:'Start Annotating'}).getAttribute('href')).toBe('/projects');expect(screen.getByRole('link',{name:'Open Dashboard'}).getAttribute('href')).toBe('/projects');expect(screen.getByRole('heading',{level:1})).toBeTruthy();
});
it('opens mobile menu, navigates to a section and closes with Escape',()=>{
 show();const toggle=screen.getByRole('button',{name:'Open navigation'});fireEvent.click(toggle);
 const mobile=screen.getByRole('navigation',{name:'Mobile navigation'});expect(toggle.getAttribute('aria-expanded')).toBe('true');fireEvent.click(within(mobile).getByRole('link',{name:'Collaboration'}));expect(screen.queryByRole('navigation',{name:'Mobile navigation'})).toBeNull();
 fireEvent.click(toggle);fireEvent.keyDown(screen.getByRole('navigation',{name:'Mobile navigation'}),{key:'Escape'});expect(toggle.getAttribute('aria-expanded')).toBe('false');expect(document.activeElement).toBe(toggle);
});
it('switches local preview geometry and selects a fictional object using the keyboard',()=>{
 const {container}=show();const preview=container.querySelector('.lp-hero-preview')! as HTMLElement;
 fireEvent.click(within(preview).getByRole('button',{name:'Polygon'}));expect(preview.querySelectorAll('polygon').length).toBe(3);
 fireEvent.keyDown(within(preview).getByRole('button',{name:'Select demo Person'}),{key:'Enter'});
 const sidebar=within(preview).getByRole('complementary',{name:'Demo objects'});
 expect(within(sidebar).getByRole('button',{name:/Person/}).getAttribute('aria-pressed')).toBe('true');
 fireEvent.click(within(preview).getByRole('button',{name:'Bounding Box'}));expect(preview.querySelectorAll('polygon').length).toBe(0);
});
it('supports showcase tab selection, arrow keys, Home and End',()=>{
 show();fireEvent.click(screen.getByRole('tab',{name:'Instance Segmentation'}));expect(screen.getByRole('tabpanel').textContent).toContain('Go beyond the bounding box.');
 fireEvent.keyDown(screen.getByRole('tab',{name:'Instance Segmentation'}),{key:'ArrowRight'});expect(screen.getByRole('tab',{name:'AI-Assisted Annotation'}).getAttribute('aria-selected')).toBe('true');
 fireEvent.keyDown(screen.getByRole('tab',{name:'AI-Assisted Annotation'}),{key:'End'});expect(screen.getByRole('tabpanel').textContent).toContain('A shared space for better data.');
 fireEvent.keyDown(screen.getByRole('tab',{name:'Team Collaboration'}),{key:'Home'});expect(screen.getByRole('tab',{name:'Object Detection'}).getAttribute('aria-selected')).toBe('true');
});
