// Settings panels: Job Search, Salary, Screening Answers, Pacing, Contact details.
// Each panel edits one section of the config object through `update(section, key, value)`.
import { useState, useEffect } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
async function getJSON(path) {
  const token = localStorage.getItem('token')
  const r = await fetch(`${API_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!r.ok) throw new Error(`${r.status}`)
  return r.json()
}

// What the bot worked out from the uploaded resume (GET /api/resume/experience)
function ResumeExperience({ enabled }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { if (enabled) getJSON('/api/resume/experience').then(setData).catch(e => setErr(e.message)) }, [enabled])
  if (!enabled) return null
  if (err) return <div className="field-hint">Could not read the resume ({err}).</div>
  if (!data) return <div className="field-hint">Reading your resume…</div>
  if (!data.found) return <div className="resume-exp warn">No resume uploaded yet. Upload one under Personal Profile so experience questions can be answered.</div>
  if (!data.roles_found) return <div className="resume-exp warn">No dated jobs found in the resume (looks for dates like "Aug 2019 – Jul 2021"). Use the manual fields below.</div>
  const NAMES = { crm: 'CRM', 'b2b sales': 'B2B sales', 'it support': 'IT support', hubspot: 'HubSpot', servicenow: 'ServiceNow',
    salesforce: 'Salesforce', zendesk: 'Zendesk', excel: 'Excel', aws: 'AWS', sql: 'SQL', 'microsoft 365': 'Microsoft 365',
    'office 365': 'Office 365', 'microsoft office': 'Microsoft Office', 'sales navigator': 'Sales Navigator', zoominfo: 'ZoomInfo' }
  const nice = (k) => NAMES[k] || (k.charAt(0).toUpperCase() + k.slice(1))
  const chips = (obj) => Object.entries(obj).map(([k, v]) => (
    <span key={k} className="exp-chip">{nice(k)} <b>{v > 0 ? `${v} yr${v === 1 ? '' : 's'}` : 'under 6 mo'}</b></span>))
  return (
    <div className="resume-exp">
      <div><b>From your resume:</b> {data.roles_found} jobs, about <b>{data.total_years}</b> years total.</div>
      <div className="exp-chips">{chips(data.areas)}</div>
      {Object.keys(data.tools).length > 0 && <div className="exp-chips"><span className="muted">Tools:</span>{chips(data.tools)}</div>}
      {data.skills_only?.length > 0 && <div className="field-hint">Listed in skills only (answers "Yes" to "do you have experience with…", years left blank): {data.skills_only.map(nice).join(', ')}</div>}
      <div className="field-hint">Years are rounded to the nearest year from your job dates, never added up twice for overlapping jobs. Anything you enter below overrides these.</div>
    </div>
  )
}

const NOT_SET = ''

// ---------------------------------------------------------------- small controls

export function ChipInput({ values = [], onChange, placeholder, suggestions = [] }) {
  const [text, setText] = useState('')
  const add = (raw) => {
    const v = raw.trim()
    if (!v || values.some(x => x.toLowerCase() === v.toLowerCase())) return
    onChange([...values, v])
  }
  const commit = () => { text.split(/;|\n/).forEach(add); setText('') }
  const unused = suggestions.filter(s => !values.some(v => v.toLowerCase() === s.toLowerCase()))
  return (
    <div>
      <div className="chip-box">
        {values.map(v => (
          <span key={v} className="chip">
            {v}
            <button type="button" aria-label={`Remove ${v}`} onClick={() => onChange(values.filter(x => x !== v))}>×</button>
          </span>
        ))}
        <input
          value={text}
          placeholder={values.length ? 'Add another…' : placeholder}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); commit() }
            if (e.key === 'Backspace' && !text && values.length) onChange(values.slice(0, -1))
          }}
          onBlur={commit}
        />
      </div>
      {unused.length > 0 && (
        <div className="chip-suggest">
          {unused.map(s => <button type="button" key={s} onClick={() => add(s)}>+ {s}</button>)}
        </div>
      )}
    </div>
  )
}

export function PillToggle({ options, values = [], onChange, multi = true }) {
  const toggle = (val) => {
    if (multi) onChange(values.includes(val) ? values.filter(v => v !== val) : [...values, val])
    else onChange(values.includes(val) ? [] : [val])
  }
  return (
    <div className="pill-row">
      {options.map(o => (
        <button type="button" key={o.value}
          className={`pill ${values.includes(o.value) ? 'on' : ''}`}
          aria-pressed={values.includes(o.value)}
          onClick={() => toggle(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div className="form-group">
      <label>{label}</label>
      {children}
      {hint && <div className="field-hint">{hint}</div>}
    </div>
  )
}

function YesNo({ value, onChange, yes = 'Yes', no = 'No' }) {
  return (
    <select value={value ?? NOT_SET} onChange={e => onChange(e.target.value)} className={!value ? 'unset' : ''}>
      <option value={NOT_SET}>Not set (skip jobs that ask)</option>
      <option value="Yes">{yes}</option>
      <option value="No">{no}</option>
    </select>
  )
}

function Choice({ value, onChange, options }) {
  return (
    <select value={value ?? NOT_SET} onChange={e => onChange(e.target.value)} className={!value ? 'unset' : ''}>
      <option value={NOT_SET}>Not set (skip jobs that ask)</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  )
}

function NumberBox({ value, onChange, min = 0, max, step = 1, placeholder, prefix }) {
  return (
    <div className="num-box">
      {prefix && <span className="num-prefix">{prefix}</span>}
      <input type="number" min={min} max={max} step={step} placeholder={placeholder}
        value={value ?? ''} onChange={e => onChange(e.target.value === '' ? '' : e.target.value)} />
    </div>
  )
}

const money = (n) => (n || n === 0) && n !== '' ? `$${Number(n).toLocaleString()}` : '—'

// ---------------------------------------------------------------- contact

export function ContactPanel({ config, update }) {
  const p = config.personal_info || {}
  const set = (k) => (v) => update('personal_info', k, v)
  return (
    <div className="settings-grid two">
      <Field label="City"><input value={p.city || ''} placeholder="Portland" onChange={e => set('city')(e.target.value)} /></Field>
      <Field label="State"><input value={p.state || ''} placeholder="OR" onChange={e => set('state')(e.target.value)} /></Field>
      <Field label="ZIP code"><input value={p.zip_code || ''} placeholder="97201" onChange={e => set('zip_code')(e.target.value)} /></Field>
      <Field label="LinkedIn profile URL"><input value={p.linkedin_url || ''} placeholder="https://www.linkedin.com/in/…" onChange={e => set('linkedin_url')(e.target.value)} /></Field>
      <Field label="Portfolio / website (optional)"><input value={p.portfolio_url || ''} onChange={e => set('portfolio_url')(e.target.value)} /></Field>
    </div>
  )
}

// ---------------------------------------------------------------- search

const KEYWORD_SUGGESTIONS = ['Account Manager', 'Account Executive', 'Inside Sales Representative', 'Customer Success Manager',
  'Sales Development Representative', 'Business Development Representative', 'Client Success', 'IT Support']
const LOCATION_SUGGESTIONS = ['Portland, OR', 'Vancouver, WA', 'Beaverton, OR', 'Seattle, WA', 'United States']
const EXCLUDE_SUGGESTIONS = ['Senior', 'Director', 'VP', 'Principal', 'Commission only', '1099', 'Intern']

export function SearchPanel({ config, update }) {
  const s = config.search || {}
  const set = (k) => (v) => update('search', k, v)
  const usOrRemoteOnly = (s.locations || []).every(l => /^(united states|remote)$/i.test(l.trim()))
  return (
    <>
      <Field label="Job titles to search" hint="Each title is searched separately. Press Enter to add.">
        <ChipInput values={s.keywords || []} onChange={set('keywords')} placeholder="e.g. Account Manager" suggestions={KEYWORD_SUGGESTIONS} />
      </Field>
      <Field label="Your cities" hint='Cities to search for on-site and hybrid jobs. On-site/hybrid jobs outside these states are skipped. Remote is set separately below.'>
        <ChipInput values={s.locations || []} onChange={set('locations')} placeholder="e.g. Portland, OR" suggestions={LOCATION_SUGGESTIONS} />
      </Field>
      <div className="settings-grid two">
        <Field label="Work type" hint="On-site/Hybrid = searched in your cities above. Remote = searched separately (see below). None selected = all.">
          <PillToggle values={s.work_types || []} onChange={set('work_types')}
            options={[{ value: 'remote', label: 'Remote' }, { value: 'hybrid', label: 'Hybrid' }, { value: 'onsite', label: 'On-site' }]} />
        </Field>
        <Field label="Distance from location" hint={usOrRemoteOnly ? 'Not used for "United States".' : undefined}>
          <select value={s.distance_miles ?? ''} onChange={e => set('distance_miles')(e.target.value ? Number(e.target.value) : null)}>
            <option value="">LinkedIn default</option>
            {[5, 10, 25, 50, 100].map(m => <option key={m} value={m}>Within {m} miles</option>)}
          </select>
        </Field>
      </div>
      <div className="settings-grid three">
        <Field label="Remote jobs" hint="Many remote jobs only hire in certain states. “My state” finds remote jobs listed for your state.">
          <select value={s.remote_scope || 'state'} onChange={e => set('remote_scope')(e.target.value)}>
            <option value="state">Remote jobs listed in my state</option>
            <option value="us">Remote jobs anywhere in the US</option>
            <option value="off">Don't search remote jobs</option>
          </select>
        </Field>
        <Field label="Local vs. remote mix" hint="Local jobs are searched and applied to first.">
          <select value={s.local_share ?? 70} onChange={e => set('local_share')(Number(e.target.value))}>
            {[100, 80, 70, 50, 30, 0].map(n => <option key={n} value={n}>{n}% local / {100 - n}% remote</option>)}
          </select>
        </Field>
        <Field label="Jobs to look at per run">
          <select value={s.max_discovered ?? 40} onChange={e => set('max_discovered')(Number(e.target.value))}>
            {[20, 30, 40, 60, 80].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Experience level" hint="None selected = any.">
        <PillToggle values={s.experience_levels || []} onChange={set('experience_levels')}
          options={[{ value: 'internship', label: 'Internship' }, { value: 'entry', label: 'Entry level' }, { value: 'associate', label: 'Associate' },
                    { value: 'mid_senior', label: 'Mid-Senior' }, { value: 'director', label: 'Director' }, { value: 'executive', label: 'Executive' }]} />
      </Field>
      <div className="settings-grid two">
        <Field label="Date posted">
          <select value={s.posted_within_days ?? 14} onChange={e => set('posted_within_days')(Number(e.target.value))}>
            <option value={1}>Past 24 hours</option><option value={3}>Past 3 days</option><option value={7}>Past week</option>
            <option value={14}>Past 2 weeks</option><option value={30}>Past month</option>
          </select>
        </Field>
        <Field label="Max applications per run">
          <select value={s.max_applications ?? 10} onChange={e => set('max_applications')(Number(e.target.value))}>
            {[3, 5, 10, 15, 20, 25].map(n => <option key={n} value={n}>{n}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Skip job titles containing" hint="Whole words, e.g. 'Senior' skips 'Senior Account Executive'.">
        <ChipInput values={s.exclude_title_words || []} onChange={set('exclude_title_words')} placeholder="e.g. Senior" suggestions={EXCLUDE_SUGGESTIONS} />
      </Field>
      <Field label="Skip companies">
        <ChipInput values={s.exclude_companies || []} onChange={set('exclude_companies')} placeholder="Company name" />
      </Field>
    </>
  )
}

// ---------------------------------------------------------------- salary

export function SalaryPanel({ config, update }) {
  const s = config.salary || {}
  const set = (k) => (v) => update('salary', k, v === '' ? null : (typeof v === 'boolean' ? v : Number(v)))
  const lo = Number(s.salary_min) || 0, hi = Number(s.salary_max) || 0
  const mid = lo && hi ? Math.round((lo + hi) / 2000) * 1000 : (lo || hi || 0)
  const answer = Number(s.salary_target) || mid
  const invalid = lo && hi && lo > hi
  return (
    <>
      <div className="settings-grid three">
        <Field label="Minimum (per year)"><NumberBox prefix="$" step={1000} value={s.salary_min} onChange={set('salary_min')} placeholder="60000" /></Field>
        <Field label="Maximum (per year)"><NumberBox prefix="$" step={1000} value={s.salary_max} onChange={set('salary_max')} placeholder="90000" /></Field>
        <Field label="Answer with" hint={`Blank = middle of your range (${money(mid)})`}>
          <NumberBox prefix="$" step={1000} value={s.salary_target} onChange={set('salary_target')} placeholder={mid ? String(mid) : ''} />
        </Field>
      </div>
      {invalid && <div className="field-error">Minimum is higher than maximum.</div>}
      <div className="salary-summary">
        {answer
          ? <>When a form asks your desired salary the bot enters <b>{money(answer)}</b>{' '}
              (about <b>${Math.round(answer / 2080)}/hr</b> if it asks hourly). Range dropdowns get the option containing that number.</>
          : <>No salary set: the bot will <b>skip</b> any job that asks for your desired salary.</>}
      </div>
      <label className="check-row">
        <input type="checkbox" checked={s.skip_if_listed_below_min !== false} onChange={e => set('skip_if_listed_below_min')(e.target.checked)} />
        <span>Skip jobs whose posted pay tops out below my minimum{lo ? ` (${money(lo)})` : ''}</span>
      </label>
      <label className="check-row">
        <input type="checkbox" checked={!!s.only_listed_salary} onChange={e => set('only_listed_salary')(e.target.checked)} />
        <span>Only search jobs that list pay <em>(LinkedIn filter, hides most postings)</em></span>
      </label>
    </>
  )
}

// ---------------------------------------------------------------- screening answers

const SKILL_SUGGESTIONS = ['Salesforce', 'HubSpot', 'CRM', 'B2B sales', 'Account management', 'Cold calling', 'Microsoft Excel', 'IT support']

function SkillYears({ value = {}, onChange }) {
  const [name, setName] = useState('')
  const [years, setYears] = useState('')
  const entries = Object.entries(value)
  const add = (n, y) => {
    const k = n.trim().toLowerCase()
    if (!k || y === '' || isNaN(Number(y))) return
    onChange({ ...value, [k]: Number(y) })
    setName(''); setYears('')
  }
  return (
    <div>
      {entries.length > 0 && (
        <div className="skill-rows">
          {entries.map(([k, v]) => (
            <div key={k} className="skill-row">
              <span>{k}</span>
              <input type="number" min="0" max="40" value={v} onChange={e => onChange({ ...value, [k]: Number(e.target.value) })} />
              <span className="muted">yrs</span>
              <button type="button" aria-label={`Remove ${k}`} onClick={() => { const c = { ...value }; delete c[k]; onChange(c) }}>×</button>
            </div>
          ))}
        </div>
      )}
      <div className="skill-row add">
        <input placeholder="Skill or tool" value={name} onChange={e => setName(e.target.value)} list="skill-suggest" />
        <datalist id="skill-suggest">{SKILL_SUGGESTIONS.map(s => <option key={s} value={s} />)}</datalist>
        <input type="number" min="0" max="40" placeholder="Years" value={years} onChange={e => setYears(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(name, years) } }} />
        <button type="button" className="btn btn-secondary" onClick={() => add(name, years)}>Add</button>
      </div>
    </div>
  )
}

const SCREENING_KEYS = ['work_authorization', 'require_sponsorship', 'located_in_us', 'remote_preference', 'onsite_ok', 'commute_ok',
  'willing_to_relocate', 'start_date', 'years_experience', 'sales_experience', 'bachelors_degree', 'high_school', 'english_proficiency',
  'background_check_ok', 'drug_test_ok', 'drivers_license', 'gender', 'race', 'veteran', 'disability']

export function ScreeningPanel({ config, update }) {
  const a = config.screening_answers || {}
  const set = (k) => (v) => update('screening_answers', k, v)
  const autoOn = (config.application || {}).auto_answer_screening !== false
  const setCount = SCREENING_KEYS.filter(k => a[k] !== undefined && a[k] !== null && String(a[k]).trim() !== '').length
  return (
    <>
      <div className="screening-head">
        <label className="check-row big">
          <input type="checkbox" checked={autoOn} onChange={e => update('application', 'auto_answer_screening', e.target.checked)} />
          <span>{autoOn ? 'Auto-answer screening questions with the answers below' : 'Off: skip every job that asks any question'}</span>
        </label>
        <div className="muted">{setCount} of {SCREENING_KEYS.length} answers set. <b>Not set</b> = the bot skips jobs that ask it. It never guesses.</div>
      </div>

      <h4>Work eligibility</h4>
      <div className="settings-grid three">
        <Field label="Legally authorized to work in the US?"><YesNo value={a.work_authorization} onChange={set('work_authorization')} /></Field>
        <Field label="Need visa sponsorship now or later?"><YesNo value={a.require_sponsorship} onChange={set('require_sponsorship')} /></Field>
        <Field label="Currently located in the US?"><YesNo value={a.located_in_us} onChange={set('located_in_us')} /></Field>
      </div>

      <h4>Location & work setup</h4>
      <div className="settings-grid four">
        <Field label="OK working remotely?"><YesNo value={a.remote_preference} onChange={set('remote_preference')} /></Field>
        <Field label="OK working on-site / hybrid?"><YesNo value={a.onsite_ok} onChange={set('onsite_ok')} /></Field>
        <Field label="OK commuting to the job's location?"><YesNo value={a.commute_ok} onChange={set('commute_ok')} /></Field>
        <Field label="Willing to relocate?"><YesNo value={a.willing_to_relocate} onChange={set('willing_to_relocate')} /></Field>
      </div>

      <h4>Experience</h4>
      <label className="check-row">
        <input type="checkbox" checked={String(a.use_resume_experience ?? 'true') !== 'false'}
          onChange={e => set('use_resume_experience')(e.target.checked ? 'true' : 'false')} />
        <span>Work out years of experience from my resume (customer service, sales, CRM, healthcare…)</span>
      </label>
      <ResumeExperience enabled={String(a.use_resume_experience ?? 'true') !== 'false'} />
      <Field label="When my resume shows no experience in something a job asks about"
        hint="Example: “How many years of Zendesk?” when Zendesk isn't on your resume.">
        <select value={a.no_experience_answer || 'answer'} onChange={e => set('no_experience_answer')(e.target.value)}>
          <option value="answer">Answer honestly (0 years / No) and apply</option>
          <option value="skip">Skip the job</option>
        </select>
      </Field>
      <div className="settings-grid three">
        <Field label="Total years of work experience" hint="Blank = use the resume total."><NumberBox value={a.years_experience} onChange={set('years_experience')} max={50} placeholder="e.g. 8" /></Field>
        <Field label="Years in sales / account mgmt / customer success" hint="Blank = use the resume."><NumberBox value={a.sales_experience} onChange={set('sales_experience')} max={50} placeholder="e.g. 6" /></Field>
        <Field label="Earliest start date">
          <Choice value={a.start_date} onChange={set('start_date')} options={['Immediately', '1 week', '2 weeks', '3 weeks', '1 month']} />
        </Field>
      </div>
      <Field label="Years with specific tools or skills"
        hint='Optional overrides for "How many years of Salesforce?" / "Do you have experience with HubSpot?". These win over the resume.'>
        <SkillYears value={a.skill_years || {}} onChange={set('skill_years')} />
      </Field>

      <h4>Education & language</h4>
      <div className="settings-grid three">
        <Field label="Completed a Bachelor's degree?"><YesNo value={a.bachelors_degree} onChange={set('bachelors_degree')} /></Field>
        <Field label="High school diploma / GED?"><YesNo value={a.high_school} onChange={set('high_school')} /></Field>
        <Field label="English proficiency">
          <Choice value={a.english_proficiency} onChange={set('english_proficiency')} options={['Native or bilingual', 'Professional', 'Conversational']} />
        </Field>
      </div>

      <h4>Checks</h4>
      <div className="settings-grid three">
        <Field label="OK with a background check?"><YesNo value={a.background_check_ok} onChange={set('background_check_ok')} /></Field>
        <Field label="OK with a drug screen?"><YesNo value={a.drug_test_ok} onChange={set('drug_test_ok')} /></Field>
        <Field label="Valid driver's license?"><YesNo value={a.drivers_license} onChange={set('drivers_license')} /></Field>
      </div>

      <h4>Voluntary self-identification (EEO)</h4>
      <div className="settings-grid four">
        <Field label="Gender"><Choice value={a.gender} onChange={set('gender')} options={['Decline', 'Male', 'Female', 'Non-binary']} /></Field>
        <Field label="Race / ethnicity"><Choice value={a.race} onChange={set('race')} options={['Decline']} /></Field>
        <Field label="Protected veteran"><Choice value={a.veteran} onChange={set('veteran')} options={['Decline', 'No', 'Yes']} /></Field>
        <Field label="Disability"><Choice value={a.disability} onChange={set('disability')} options={['Decline', 'No', 'Yes']} /></Field>
      </div>
      <div className="field-hint">"Decline" picks the "I don't wish to answer" option on the form.</div>
    </>
  )
}

// ---------------------------------------------------------------- pacing

export function PacingPanel({ config, update }) {
  const p = config.application || {}
  const set = (k) => (v) => update('application', k, Number(v))
  const lo = Number(p.min_delay ?? 30), hi = Number(p.max_delay ?? 90)
  return (
    <div className="settings-grid two">
      <Field label="Wait between applications: at least">
        <select value={lo} onChange={e => set('min_delay')(e.target.value)}>
          {[15, 30, 60, 90, 120, 180].map(n => <option key={n} value={n}>{n} seconds</option>)}
        </select>
      </Field>
      <Field label="…and at most" hint={hi < lo ? 'Must be at least the minimum.' : 'A random wait in this range looks less automated.'}>
        <select value={hi} onChange={e => set('max_delay')(e.target.value)}>
          {[30, 60, 90, 120, 180, 300].map(n => <option key={n} value={n}>{n} seconds</option>)}
        </select>
      </Field>
    </div>
  )
}

// ---------------------------------------------------------------- validation used by Save

export function validateSettings(config) {
  const errs = []
  const s = config.salary || {}
  if (s.salary_min && s.salary_max && Number(s.salary_min) > Number(s.salary_max)) errs.push('Salary minimum is higher than the maximum.')
  const app = config.application || {}
  if (Number(app.max_delay) < Number(app.min_delay)) errs.push('Maximum wait must be at least the minimum wait.')
  if (!(config.search?.keywords || []).length) errs.push('Add at least one job title to search.')
  const remoteOnlyUS = (config.search?.remote_scope === 'us') && (config.search?.work_types || []).join() === 'remote'
  if (!(config.search?.locations || []).length && !remoteOnlyUS) errs.push('Add at least one city (or choose Remote only + anywhere in the US).')
  return errs
}
