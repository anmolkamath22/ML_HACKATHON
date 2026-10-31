import { Dices, Sparkles } from 'lucide-react'
import type { GenerationOptions } from '../types'

export const MAX_PROMPT_LENGTH = 500
export const QUALITY_PRESETS = [{ steps: 30, label: 'Fast · 30 steps' }, { steps: 50, label: 'Balanced · 50 steps' }, { steps: 75, label: 'Best · 75 steps' }]
type Props = {
  prompt: string; onPrompt: (value: string) => void; options: GenerationOptions; onOptions: (value: GenerationOptions) => void
  onGenerate: () => void; submitting: boolean; disabledReason: string; error: string
}

export function GenerateControls({ prompt, onPrompt, options, onOptions, onGenerate, submitting, disabledReason, error }: Props) {
  const set = (patch: Partial<GenerationOptions>) => onOptions({ ...options, ...patch })
  return <div className="generate-controls">
    <label className="field-label" htmlFor="prompt">Description <span>optional</span></label>
    <textarea id="prompt" maxLength={MAX_PROMPT_LENGTH} placeholder="e.g. a small wooden toy boat" value={prompt} onChange={event => onPrompt(event.target.value)}/>
    <div className="field-hint"><span>Saved with the job and shown in history. InstantMesh builds geometry from the image only.</span><span>{prompt.length}/{MAX_PROMPT_LENGTH}</span></div>
    <details className="options-panel">
      <summary>Generation options</summary>
      <div className="options-grid">
        <label>Background<select value={options.remove_background ? 'rembg' : 'cutout'} onChange={event => set({ remove_background: event.target.value === 'rembg' })}>
          <option value="cutout">OpenCV cutout (sketches, plain backgrounds)</option><option value="rembg">rembg removal (photos)</option></select></label>
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
