import { Dices, Sparkles } from 'lucide-react'
import type { RequestedOptions } from '../types'

export const MAX_PROMPT_LENGTH = 500
export const QUALITY_PRESETS = [{ steps: 30, label: 'Fast · 30 steps' }, { steps: 50, label: 'Balanced · 50 steps' }, { steps: 75, label: 'Best · 75 steps' }]
type Props = {
  prompt: string; onPrompt: (value: string) => void; options: RequestedOptions; onOptions: (value: RequestedOptions) => void
  onGenerate: () => void; submitting: boolean; disabledReason: string; error: string; controlnetEnabled: boolean
}
const toChoice = (value: boolean | null) => value === null ? 'auto' : value ? 'on' : 'off'
const fromChoice = (value: string) => value === 'auto' ? null : value === 'on'

export function GenerateControls({ prompt, onPrompt, options, onOptions, onGenerate, submitting, disabledReason, error, controlnetEnabled }: Props) {
  const set = (patch: Partial<RequestedOptions>) => onOptions({ ...options, ...patch })
  return <div className="generate-controls">
    <label className="field-label" htmlFor="prompt">Description <span>optional</span></label>
    <textarea id="prompt" maxLength={MAX_PROMPT_LENGTH} placeholder="e.g. a small wooden toy boat with a red sail" value={prompt} onChange={event => onPrompt(event.target.value)}/>
    <div className="field-hint"><span>{controlnetEnabled ? 'Guides colour, material and style of the AI image. The shape always comes from your sketch.' : 'Saved with the job. AI refinement is turned off on this server, so the description does not change the model.'}</span><span>{prompt.length}/{MAX_PROMPT_LENGTH}</span></div>
    <details className="options-panel">
      <summary>Generation options</summary>
      <div className="options-grid">
        <label>AI refinement (ControlNet)<select value={toChoice(options.refine_sketch)} disabled={!controlnetEnabled} onChange={event => set({ refine_sketch: fromChoice(event.target.value) })}>
          <option value="auto">Auto: on for sketches, off for photos</option><option value="on">On: turn the sketch into an image first</option><option value="off">Off: use the sketch directly</option></select></label>
        <label>Background<select value={toChoice(options.remove_background)} onChange={event => set({ remove_background: fromChoice(event.target.value) })}>
          <option value="auto">Auto</option><option value="off">OpenCV cutout (plain backgrounds)</option><option value="on">rembg removal (photos)</option></select></label>
        <label>Quality<select value={options.diffusion_steps} onChange={event => set({ diffusion_steps: Number(event.target.value) })}>
          {QUALITY_PRESETS.map(preset => <option key={preset.steps} value={preset.steps}>{preset.label}</option>)}</select></label>
        <label>Seed<span className="seed-row"><input type="number" min={0} max={2147483647} value={options.seed} onChange={event => set({ seed: Math.max(0, Math.min(2147483647, Math.floor(Number(event.target.value) || 0))) })}/>
          <button type="button" className="icon-button" aria-label="Random seed" onClick={() => set({ seed: Math.floor(Math.random() * 100000) })}><Dices size={15}/></button></span></label>
        <label className="check-row"><input type="checkbox" checked={options.export_texture} onChange={event => set({ export_texture: event.target.checked })}/>Bake a texture map (slower; vertex colours otherwise)</label>
      </div>
    </details>
    <div className="generate-row">
      <button className="primary-button generate-button" disabled={submitting || !!disabledReason} onClick={onGenerate}><Sparkles size={16}/>{submitting ? 'Submitting…' : 'Generate 3D'}</button>
      {disabledReason && !submitting && <span className="field-hint">{disabledReason}</span>}
    </div>
    {error && <div className="notice-error" role="alert">{error}</div>}
  </div>
}
