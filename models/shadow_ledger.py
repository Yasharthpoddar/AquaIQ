"""Isolated append-only direct-six-month shadow evidence; never fits a model.

No DB, active checkpoint, or estimator imports. The real HGB slot is deliberately
abstained pending explicit approval of a separate frozen-artifact workflow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd

from models.prospective_validation import checksum

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'aquaiq-direct-shadow-v1'
INDIA = 'Asia/Kolkata'
LANES = ('synthetic', 'retrospective', 'prospective')
MODELS = ('hist_gradient_boosting', 'persistence', 'seasonal_naive')
CANDIDATE = {'candidate_id':'hist_gradient_boosting-2-delta',
             'family':'hist_gradient_boosting', 'target_form':'delta',
             'parameters':{'max_iter':250, 'learning_rate':.05, 'max_leaf_nodes':31,
                           'min_samples_leaf':50, 'l2_regularization':20.}}
FEATURES = ['gwl_current','gwl_lag_3mo','gwl_lag_6mo','rainfall_current',
            'rainfall_3mo_avg','monsoon_deficit_pct','temperature','evapotranspiration',
            'water_balance_proxy','season_Kharif','season_Rabi','season_Zaid',
            'origin_month_sin','origin_month_cos']
NUMERIC = FEATURES[:9]
INPUTS = [*NUMERIC, 'seasonal_reference']
UNITS = {name:('m_bgl' if name.startswith('gwl_') or name=='seasonal_reference'
               else 'degC' if name=='temperature' else 'percent' if name=='monsoon_deficit_pct'
               else 'mm/month') for name in INPUTS}


class DuplicateIssuance(FileExistsError):
    """An issuance key is already reserved, including interrupted writes."""


def utc_now():
    return datetime.now(timezone.utc)


def _time(value):
    if value is None or isinstance(value, bool):
        raise ValueError('Timezone-aware timestamp required')
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError('Invalid timestamp') from error
    if pd.isna(result) or result.tz is None:
        raise ValueError('Timezone-aware timestamp required')
    return result.tz_convert('UTC')


def _text(value, field):
    if not isinstance(value,str) or not value.strip() or value!=value.strip():
        raise ValueError(f'{field} requires a nonempty trimmed string')
    return value


def _hash(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('SHA256 identity required')
    return value


def _number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Finite numeric value required; booleans are not measurements')
    return float(value)


def _month(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',value):
        raise ValueError('Month must be YYYY-MM')
    return pd.Period(value,freq='M')


def _clone(value):
    return json.loads(json.dumps(value,allow_nan=False))


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def locked_contract():
    """Verify the saved selection, without importing its training code."""
    base = ROOT/'reports/candidates/six_month_selection_20261017/experiment_v2'
    lock = json.loads((base/'selection_lock.json').read_text(encoding='utf-8'))
    plan = json.loads((base/'protocol.json').read_text(encoding='utf-8'))
    if (lock['selected_ml']!=CANDIDATE or plan['final']['train_target_cutoff']!='2018-12-31'
            or plan['features']!=FEATURES or lock['protocol_sha256']!=file_sha(base/'protocol.json')):
        raise ValueError('Locked candidate settings, training cutoff or protocol differs')
    return {'candidate':_clone(CANDIDATE),'train_target_cutoff':'2018-12-31',
            'training_pairs':14817,'features':FEATURES.copy(),'random_state':42,
            'early_stopping':False,'prediction_policy':'max(0, origin_depth + predicted_delta)',
            'native_missing_handling':True,'selection_lock_sha256':file_sha(base/'selection_lock.json'),
            'protocol_sha256':file_sha(base/'protocol.json'),
            'training_feature_csv_sha256':plan['feature_csv_sha256'],
            'training_feature_generation':plan['generation'],'software':plan['software'],
            'preprocessing_state_sha256':None,
            'model_sha256':None,'model_artifact_status':'not_approved_not_created'}


def _panel(panel):
    panel = _clone(panel)
    if not isinstance(panel,dict):
        raise ValueError('Registered panel mapping required')
    for field in ('panel_id','version_id'):
        _text(panel.get(field),field)
    _hash(panel.get('geography_sha256'))
    panel['registered_at'] = _time(panel.get('registered_at')).isoformat()
    if panel.get('units')!='m_bgl' or panel.get('datum')!='below_ground_level':
        raise ValueError('Panel requires explicit m_bgl below-ground datum')
    wells = panel.get('wells')
    if not isinstance(wells,list) or not wells:
        raise ValueError('A registered well panel is required')
    identities=[]
    for well in wells:
        if not isinstance(well,dict):
            raise ValueError('Well member mapping required')
        identities.append(_text(well.get('well_id'),'well_id'))
        if _number(well.get('weight'))<=0:
            raise ValueError('Well weights must be positive')
    if len(identities)!=len(set(identities)) or not math.isclose(sum(w['weight'] for w in wells),1.,abs_tol=1e-12):
        raise ValueError('Unique well identities and weights summing to one required')
    panel['wells']=sorted(wells,key=lambda x:x['well_id'])
    return panel


def panel_fingerprint(panel):
    return checksum(_panel(panel))


def _seal(value):
    value=_clone(value)
    value['record_sha256']=checksum(value)
    return value


def _unseal(value):
    if checksum({k:v for k,v in value.items() if k!='record_sha256'})!=value.get('record_sha256'):
        raise ValueError('Record checksum mismatch; immutable evidence was modified')
    return value


def _write_new(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
        stream.flush()
        import os
        os.fsync(stream.fileno())


class FileLedger:
    """Exclusive directory reservations plus sealed create-only JSON records.

    `workspace` and `clock` are injectable for isolated tests. CLI always uses
    the repository workspace and real clock; it has no backdating option.
    """
    def __init__(self,path,*,workspace=ROOT,clock=utc_now):
        parent=(Path(workspace)/'reports/candidates').resolve()
        self.path=Path(path).resolve()
        if (not self.path.is_relative_to(parent) or self.path==parent
                or not self.path.relative_to(parent).parts[0].startswith('shadow_')):
            raise ValueError('Ledger must be inside a dedicated reports/candidates/shadow_* directory')
        self.clock=clock
        self._header=None

    @classmethod
    def create(cls,path,*,lane,campaign_id,workspace=ROOT,clock=utc_now):
        ledger=cls(path,workspace=workspace,clock=clock)
        if lane not in LANES:
            raise ValueError('Unknown evidence lane')
        _text(campaign_id,'campaign_id')
        header=_seal({'schema_version':VERSION,'kind':'ledger_header','lane':lane,
            'campaign_id':campaign_id,'created_at_utc':_time(clock()).isoformat(),
            'contract':locked_contract(),'configuration_sha256':file_sha(ROOT/'config.yaml'),
            'feature_pipeline_sha256':file_sha(ROOT/'preprocessing/features.py'),
            'causal_preprocessing_sha256':file_sha(ROOT/'preprocessing/pipeline.py'),
            'implementation_sha256':file_sha(Path(__file__)),
            'real_hgb_enabled':False,'synthetic':lane=='synthetic'})
        ledger.path.parent.mkdir(parents=True,exist_ok=True)
        ledger.path.mkdir(exist_ok=False)
        _write_new(ledger.path/'ledger.json',header)
        for name in ('forecasts','labels','evaluations','locks'):
            (ledger.path/name).mkdir()
        ledger._header=header
        return ledger

    @classmethod
    def open(cls,path,*,workspace=ROOT,clock=utc_now):
        ledger=cls(path,workspace=workspace,clock=clock)
        ledger._header=ledger._load_header()
        return ledger

    @property
    def header(self):
        return _clone(self._header)

    def _child(self,*parts):
        path=self.path.joinpath(*parts).resolve()
        if not path.is_relative_to(self.path):
            raise ValueError('Ledger path escapes its isolated root')
        return path

    def _load_header(self):
        value=_unseal(json.loads(self._child('ledger.json').read_text(encoding='utf-8')))
        if (value.get('schema_version')!=VERSION or value.get('kind')!='ledger_header'
                or value.get('lane') not in LANES or value.get('contract')!=locked_contract()
                or value.get('real_hgb_enabled') is not False):
            raise ValueError('Unsupported or changed ledger contract')
        if self._header and value!=self._header:
            raise ValueError('Ledger header changed after opening')
        return value

    def _write_entry(self,category,identity,payload):
        header=self._load_header()
        if header['implementation_sha256']!=file_sha(Path(__file__)):
            raise ValueError('Ledger implementation changed; start a separately registered campaign')
        key=checksum(identity)
        directory=self._child(category,key)
        try:
            directory.mkdir(exist_ok=False)
        except FileExistsError as error:
            raise DuplicateIssuance(f'Duplicate {category} identity already reserved') from error
        record=_seal({**payload,'schema_version':VERSION,'kind':category,
                      'entry_id':key,'identity':identity,'ledger_sha256':header['record_sha256']})
        _write_new(directory/'record.json',record)
        archived=_time(self.clock())
        if archived<_time(payload['recorded_at_utc']):
            raise ValueError('Clock moved backwards; entry remains visibly incomplete')
        commit=_seal({'schema_version':VERSION,'record_sha256_bound':record['record_sha256'],
                      'archived_at_utc':archived.isoformat()})
        _write_new(directory/'commit.json',commit)
        return {'record':_clone(record),'commit':_clone(commit)}

    def _entries(self,category):
        self._load_header()
        outputs=[]
        for directory in sorted(self._child(category).iterdir()):
            if not directory.is_dir():
                raise ValueError('Unexpected ledger entry')
            directory=self._child(category,directory.name)
            if not (directory/'record.json').is_file() or not (directory/'commit.json').is_file():
                raise ValueError('Incomplete reserved entry; manual recovery required, never overwrite it')
            record=_unseal(json.loads((directory/'record.json').read_text(encoding='utf-8')))
            commit=_unseal(json.loads((directory/'commit.json').read_text(encoding='utf-8')))
            if (record.get('kind')!=category or record.get('schema_version')!=VERSION
                    or record.get('entry_id')!=directory.name or checksum(record.get('identity'))!=directory.name
                    or record.get('ledger_sha256')!=self._header['record_sha256']
                    or commit.get('record_sha256_bound')!=record['record_sha256']
                    or _time(commit['archived_at_utc'])<_time(record['recorded_at_utc'])):
                raise ValueError('Ledger identity, commit or checksum differs')
            outputs.append({'record':record,'commit':commit})
        return outputs

    def forecasts(self):
        return self._entries('forecasts')

    def labels(self):
        return self._entries('labels')

    def _evidence(self,value):
        expected='synthetic_fixture' if self._header['lane']=='synthetic' else 'real_observation'
        if value!=expected:
            raise ValueError('Synthetic fixtures and real evidence lanes cannot be mixed')

    def _source(self,supplied,cutoff):
        source=_clone(supplied)
        if not isinstance(source,dict):
            raise ValueError('Source version mapping required')
        for name in ('source_id','version_id'):
            _text(source.get(name),name)
        _hash(source.get('sha256'))
        published,received=(_time(source.get(k)) for k in ('published_at','received_at'))
        if published>received or received>cutoff:
            raise ValueError('Source publication/receipt unavailable at issuance or evaluation')
        if self._header['lane']!='synthetic' and 'synthetic' in source['source_id'].lower():
            raise ValueError('Synthetic source cannot enter a real evidence lane')
        source.update(published_at=published.isoformat(),received_at=received.isoformat())
        return source

    def append_forecast(self,snapshot):
        snapshot=_clone(snapshot)
        if not isinstance(snapshot,dict):
            raise ValueError('Forecast snapshot mapping required')
        allowed={'district_id','origin_month','target_month','evidence_kind','panel','sources','inputs',
                 'issued_at','synthetic_hgb_prediction'}
        if set(snapshot)-allowed:
            raise ValueError('Unknown forecast fields; caller predictions and model overrides are forbidden')
        recorded=_time(self.clock())
        self._evidence(snapshot.get('evidence_kind'))
        if self._header['lane']=='prospective' and 'issued_at' in snapshot:
            raise ValueError('Prospective caller backdating is forbidden; actual clock determines issuance')
        issued=_time(snapshot.get('issued_at',recorded))
        if issued>recorded:
            raise ValueError('Issue time is in the future')
        if issued.tz_convert(INDIA).date()<=pd.Timestamp('2018-12-31').date():
            raise ValueError('Locked model training cutoff must precede issuance')
        if self._header['lane']!='synthetic' and 'synthetic_hgb_prediction' in snapshot:
            raise ValueError('Synthetic predictor cannot enter a real evidence lane')
        district=_text(snapshot.get('district_id'),'district_id')
        origin=_month(snapshot.get('origin_month'))
        target=str(origin+6)
        if 'target_month' in snapshot and snapshot['target_month']!=target:
            raise ValueError('Target must be exactly origin plus six calendar months')
        if origin.start_time.tz_localize(INDIA).tz_convert('UTC')>issued:
            raise ValueError('Forecast origin month is in the future')
        target_start=(origin+6).start_time.tz_localize(INDIA).tz_convert('UTC')
        if self._header['lane']=='prospective' and target_start<=recorded:
            raise ValueError('Prospective target must follow actual issuance')
        panel=_panel(snapshot.get('panel'))
        if _time(panel['registered_at'])>issued:
            raise ValueError('Well panel was not registered at issuance')
        if self._header['lane']!='synthetic' and any('synthetic' in w['well_id'].lower() for w in panel['wells']):
            raise ValueError('Synthetic well panel cannot enter a real evidence lane')
        sources={}
        for supplied in snapshot.get('sources',[]):
            source=self._source(supplied,issued)
            key=(source['source_id'],source['version_id'])
            if key in sources:
                raise ValueError('Duplicate source version')
            sources[key]=source
        provided=snapshot.get('inputs')
        if not isinstance(provided,dict) or set(provided)-set(INPUTS):
            raise ValueError('Unknown or missing input snapshot mapping')
        inputs={}
        for name in INPUTS:
            item=_clone(provided.get(name,{'value':None,'missing_reason':'not_supplied'}))
            if not isinstance(item,dict):
                raise ValueError('Input envelope mapping required')
            if item.get('value') is None:
                _text(item.get('missing_reason'),'missing_reason')
                for field in ('observed_at','period_end','available_at'):
                    if field in item and _time(item[field])>issued:
                        raise ValueError('Missing-input metadata is unavailable at issuance')
                inputs[name]=item
                continue
            item['value']=_number(item['value'])
            if item.get('units')!=UNITS[name] or not isinstance(item.get('is_observed'),bool):
                raise ValueError('Input units and explicit observation flag required')
            expected=str(origin-3 if name=='gwl_lag_3mo' else origin-6 if name in ('gwl_lag_6mo','seasonal_reference') else origin)
            if item.get('month')!=expected:
                raise ValueError('Input calendar month does not match origin/lag/seasonal identity')
            source=sources.get((item.get('source_id'),item.get('version_id')))
            if source is None:
                raise ValueError('Input references an unknown source version')
            observed,end,available=(_time(item.get(k)) for k in ('observed_at','period_end','available_at'))
            if not (observed<=end<=_time(source['published_at'])<=_time(source['received_at'])<=available<=issued):
                raise ValueError('Input observation/period/publication/receipt/availability is late or inconsistent')
            month_end=(_month(expected)+1).start_time.tz_localize(INDIA).tz_convert('UTC')
            if end>=month_end:
                raise ValueError('Input includes future calendar information')
            if name in NUMERIC[3:] and end<month_end-pd.Timedelta(seconds=1):
                raise ValueError('Complete origin-month weather period is required; partial-month weather is unavailable')
            if name.startswith('gwl_') or name=='seasonal_reference':
                measured_month=observed.tz_convert(INDIA).strftime('%Y-%m')
                age=_month(expected).ordinal-_month(measured_month).ordinal
                if (item['is_observed'] and age!=0) or (not item['is_observed'] and not 1<=age<=3):
                    raise ValueError('Groundwater observation date conflicts with observed/bounded-fill provenance')
                if 'panel_sha256' in item and item['panel_sha256']!=panel_fingerprint(panel):
                    raise ValueError('Input well panel differs from the registered panel')
            item.update(observed_at=observed.isoformat(),period_end=end.isoformat(),available_at=available.isoformat())
            inputs[name]=item
        predictions={}
        for model,input_name,reason in [('persistence','gwl_current','missing_or_unobserved_origin'),
                                         ('seasonal_naive','seasonal_reference','missing_or_unobserved_seasonal')]:
            item=inputs[input_name]
            known=item.get('value') is not None and item.get('is_observed') is True
            predictions[model]={'status':'predicted' if known else 'abstained',
                'prediction_m_bgl':item.get('value') if known else None,'reason_codes':[] if known else [reason],
                'model_sha256':checksum({'baseline':model,'definition':'observed origin' if model=='persistence' else 'exact target minus 12 months','version':VERSION})}
        ml={'status':'abstained','prediction_m_bgl':None,'reason_codes':['shadow_artifact_not_approved'],
            'model_sha256':None,'candidate_id':CANDIDATE['candidate_id'],'prediction_origin':'unavailable'}
        if self._header['lane']=='synthetic' and 'synthetic_hgb_prediction' in snapshot:
            if predictions['persistence']['status']=='predicted':
                ml.update(status='predicted',prediction_m_bgl=max(0.,_number(snapshot['synthetic_hgb_prediction'])),
                    reason_codes=[],model_sha256=checksum({'synthetic_stub':VERSION}),
                    prediction_origin='synthetic_fixture_stub_not_trained_hgb')
            else:
                ml['reason_codes']=['missing_or_unobserved_origin']
        predictions['hist_gradient_boosting']=ml
        vector={name:inputs[name]['value'] for name in NUMERIC}
        month=origin.month
        vector.update(season_Kharif=int(6<=month<=10),season_Rabi=int(month in (11,12,1,2,3)),
            season_Zaid=int(month in (4,5)),origin_month_sin=math.sin(2*math.pi*month/12),
            origin_month_cos=math.cos(2*math.pi*month/12))
        identity={'campaign_id':self._header['campaign_id'],'district_id':district,
                  'origin_month':str(origin),'target_month':target}
        return self._write_entry('forecasts',identity,{'recorded_at_utc':recorded.isoformat(),
            'issued_at_utc':issued.isoformat(),'lane':self._header['lane'],'evidence_kind':snapshot['evidence_kind'],
            'district_id':district,'origin_month':str(origin),'target_month':target,'horizon_months':6,
            'units':'m_bgl','panel':panel,'panel_sha256':panel_fingerprint(panel),
            'sources':list(sources.values()),'inputs':inputs,'feature_values':vector,
            'configuration_sha256':self._header['configuration_sha256'],
            'feature_pipeline_sha256':self._header['feature_pipeline_sha256'],
            'causal_preprocessing_sha256':self._header['causal_preprocessing_sha256'],
            'candidate_configuration_sha256':checksum(self._header['contract']),
            'predictions':predictions,'paired_prediction_eligible':all(x['status']=='predicted' for x in predictions.values()),
            'prospective_forecast_archive':self._header['lane']=='prospective',
            'prospective_skill_established':False})

    def append_label(self,label):
        label=_clone(label)
        if not isinstance(label,dict):
            raise ValueError('Label mapping required')
        identity={key:_text(label.get(key),key) for key in ('district_id','label_id')}
        identity['month']=str(_month(label.get('month')))
        with self._label_lock(identity):
            return self._append_label_locked(label)

    @contextmanager
    def _label_lock(self,identity):
        """Serialize a label's revision chain; no competing revision branches."""
        directory=self._child('locks',checksum(identity))
        try:
            directory.mkdir(exist_ok=False)
        except FileExistsError as error:
            raise DuplicateIssuance('Label series is busy or has an interrupted revision; retry or review its lock') from error
        try:
            yield
        finally:
            directory.rmdir()

    def _append_label_locked(self,label):
        label=_clone(label)
        if not isinstance(label,dict):
            raise ValueError('Label mapping required')
        if set(label)&{'record_sha256','schema_version','kind','entry_id','identity','ledger_sha256','recorded_at_utc','lane'}:
            raise ValueError('Caller cannot supply reserved ledger identity or timestamp fields')
        now=_time(self.clock())
        self._evidence(label.get('evidence_kind'))
        for name in ('district_id','label_id','revision_id'):
            _text(label.get(name),name)
        month=str(_month(label.get('month')))
        if (label.get('units')!='m_bgl' or label.get('datum_verified') is not True
                or label.get('is_observed') is not True or label.get('is_imputed') is not False):
            raise ValueError('Verified observed, non-imputed m_bgl labels required')
        _hash(label.get('panel_sha256'))
        label['depth_m_bgl']=_number(label.get('depth_m_bgl'))
        start,end,available=(_time(label.get(k)) for k in ('observed_start_at','observed_end_at','available_at'))
        source=self._source(label.get('source'),now)
        if not (start<=end<=_time(source['published_at'])<=_time(source['received_at'])<=available<=now):
            raise ValueError('Label acquisition/publication/receipt/availability is future or inconsistent')
        if any(value.tz_convert(INDIA).strftime('%Y-%m')!=month for value in (start,end)):
            raise ValueError('Label acquisition does not match its target month')
        existing=[entry['record'] for entry in self.labels() if entry['record']['district_id']==label['district_id']
                  and entry['record']['month']==month and entry['record']['label_id']==label['label_id']]
        if any(entry['revision_id']==label['revision_id'] for entry in existing):
            raise DuplicateIssuance('Duplicate labels identity already reserved')
        previous=label.get('supersedes_sha256')
        if existing:
            superseded={entry.get('supersedes_sha256') for entry in existing}
            tips=[entry for entry in existing if entry['record_sha256'] not in superseded]
            if len(tips)!=1 or previous!=tips[0]['record_sha256']:
                raise ValueError('Revised label must reference the latest parent in a linear immutable vintage chain')
            predecessor=tips[0]
            if available<_time(predecessor['available_at']):
                raise ValueError('Revision availability precedes its parent vintage')
        elif previous is not None:
            raise ValueError('Unknown parent label revision')
        identity={key:label[key] for key in ('district_id','label_id','revision_id')}
        identity['month']=month
        label.update(recorded_at_utc=now.isoformat(),observed_start_at=start.isoformat(),
                     observed_end_at=end.isoformat(),available_at=available.isoformat(),source=source,
                     lane=self._header['lane'])
        return self._write_entry('labels',identity,label)

    def verify(self):
        self._load_header()
        if any(self._child('locks').iterdir()):
            raise ValueError('Busy or interrupted label revision lock; verify after writer completion or manual review')
        counts={name:len(self._entries(name)) for name in ('forecasts','labels','evaluations')}
        return {'schema_version':VERSION,'lane':self._header['lane'],'campaign_id':self._header['campaign_id'],
                'counts':counts,'verified':True,'tamper_model':'local hashes; not trusted timestamping or write-once media',
                'model_fitted':False,'sufficient_for_operational_use':False}

    def evaluate(self,*,label_policy='first',persist=True):
        if label_policy not in ('first','latest'):
            raise ValueError('Label vintage policy must be first or latest')
        now=_time(self.clock())
        forecasts,labels=self.forecasts(),self.labels()
        if any(_time(item['commit']['archived_at_utc'])>now for item in [*forecasts,*labels]):
            raise ValueError('Evaluation clock precedes archived evidence')
        cases,pending=[],[]
        for envelope in forecasts:
            record,commit=envelope['record'],envelope['commit']
            choices=[entry['record'] for entry in labels if entry['record']['district_id']==record['district_id']
                     and entry['record']['month']==record['target_month'] and _time(entry['record']['available_at'])<=now]
            if not choices:
                pending.append({'case_id':record['entry_id'],'district_id':record['district_id'],
                                'target_month':record['target_month'],'reason':'awaiting_observed_label'})
                continue
            # Multiple unrelated label series cannot be selected opportunistically.
            if len({entry['label_id'] for entry in choices})!=1:
                raise ValueError('Ambiguous label series for one forecast; adjudicate in a new registered evaluation')
            roots=[choice for choice in choices if choice.get('supersedes_sha256') is None]
            if len(roots)!=1:
                raise ValueError('Ambiguous first label vintage')
            parents={choice.get('supersedes_sha256') for choice in choices}
            tips=[choice for choice in choices if choice['record_sha256'] not in parents]
            if len(tips)!=1:
                raise ValueError('Ambiguous latest label vintage')
            label=roots[0] if label_policy=='first' else tips[0]
            archived=_time(commit['archived_at_utc'])
            start=_time(label['observed_start_at'])
            if self._header['lane']=='synthetic':
                classification='synthetic'
            elif self._header['lane']=='retrospective' or start<=archived:
                classification='retrospective'
            elif start>=archived.tz_convert(INDIA)+pd.DateOffset(months=6):
                classification='prospective_six_full_month'
            else:
                classification='prospective_nominal_six_month'
            reasons=[]
            if label['panel_sha256']!=record['panel_sha256']:
                reasons.append('well_panel_mismatch')
            if not record['paired_prediction_eligible']:
                reasons.append('missing_prediction_or_baseline')
            cases.append({'case_id':record['entry_id'],'district_id':record['district_id'],
                'target_month':record['target_month'],'classification':classification,
                'forecast_sha256':record['record_sha256'],'label_sha256':label['record_sha256'],
                'actual_m_bgl':label['depth_m_bgl'],'predictions':record['predictions'],
                'paired_eligible':not reasons,'reason_codes':reasons,
                'observed_start_at':label['observed_start_at'],'archived_at_utc':commit['archived_at_utc'],
                'actual_lead_days':float((start-archived).total_seconds()/86400)})
        cohorts={}
        for name in sorted({case['classification'] for case in cases}):
            selected=[case for case in cases if case['classification']==name]
            paired=[case for case in selected if case['paired_eligible']]
            measured={}
            for model in MODELS:
                errors=[case['predictions'][model]['prediction_m_bgl']-case['actual_m_bgl'] for case in paired]
                measured[model]={'n':len(errors),'mae_m':sum(map(abs,errors))/len(errors) if errors else None,
                                 'rmse_m':math.sqrt(sum(e*e for e in errors)/len(errors)) if errors else None}
            cohorts[name]={'n':len(selected),'paired_n':len(paired),'models':measured}
        report={'recorded_at_utc':now.isoformat(),'evaluated_at_utc':now.isoformat(),
                'lane':self._header['lane'],'label_policy':label_policy,'cases':cases,'cohorts':cohorts,
                'pending':pending,'sufficient_for_operational_use':False,
                'interpretation':'Synthetic scores are fixtures; retrospective scores are historical; prospective skill requires genuinely new observed acquisitions and preregistered analysis.',
                'model_fitted':False,'production_changes_made':False}
        if persist:
            return self._write_entry('evaluations',{'report_sha256':checksum(report)},report)['record']
        return report
