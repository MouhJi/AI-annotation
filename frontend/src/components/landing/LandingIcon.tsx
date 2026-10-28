export type LandingIconName = 'bounding-box' | 'polygon' | 'sparkle' | 'users-three' | 'export' | 'cursor' | 'check' | 'pause' | 'play' | 'arrow-up-right';

export default function LandingIcon({name}:{name:LandingIconName}) {
  return <span className="lp-icon" data-icon={name} aria-hidden="true"/>;
}
