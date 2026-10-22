#!/usr/bin/env python3
"""Offline evidence-contract checks; NOT a fact checker or web retriever."""
import argparse
import json
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlsplit

DOMAINS = {
    'Apple': ('apple.com',),
    'OpenAI': ('openai.com',),
    'Google': ('google.com', 'about.google', 'blog.google', 'deepmind.google', 'abc.xyz', 'ai.google.dev'),
    'Anthropic': ('anthropic.com', 'claude.com'),
    'Meta': ('meta.com', 'fb.com', 'atmeta.com', 'meta.ai', 'muse.ai'),
}
STATUSES = {'verified', 'corroborated', 'provisional', 'unknown'}

def text_value(value):
    return isinstance(value, str) and bool(value.strip())

def member(value, options):
    return isinstance(value, str) and value in options

def text_list(value):
    return isinstance(value, list) and bool(value) and all(text_value(v) for v in value)

def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp must be a string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return parsed

def official_host(company, url):
    try:
        u = urlsplit(url)
        host = (u.hostname or '').lower()
        return isinstance(company, str) and u.scheme == 'https' and not u.username and not u.password and any(
            host == d or host.endswith('.' + d) for d in DOMAINS.get(company, ()))
    except (ValueError, TypeError, AttributeError):
        return False

def check(data):
    errors, warnings = [], []
    if not isinstance(data, dict):
        return {'ok': False, 'errors': ['root must be object'], 'warnings': []}
    try:
        cutoff = timestamp(data.get('as_of'))
    except (ValueError, TypeError):
        return {'ok': False, 'errors': ['as_of requires ISO timestamp with timezone'], 'warnings': []}
    claims = data.get('claims')
    if not isinstance(claims, list) or not claims:
        return {'ok': False, 'errors': ['claims must be nonempty array'], 'warnings': []}
    seen = set()
    for i, c in enumerate(claims):
        tag = f'claims[{i}]'
        if not isinstance(c, dict):
            errors.append(tag + ': object required'); continue
        for key in ('id', 'company', 'kind', 'claim', 'status', 'scope', 'sources', 'conflict', 'limitation'):
            if key not in c:
                errors.append(f'{tag}: missing {key}')
        cid = c.get('id')
        if not isinstance(cid, str) or not cid or cid in seen:
            errors.append(tag + ': id must be nonempty and unique')
        else:
            seen.add(cid)
        for key in ('claim', 'scope'):
            if not isinstance(c.get(key), str) or not c[key].strip():
                errors.append(f'{tag}: {key} must be nonempty text')
        if not member(c.get('company'), DOMAINS):
            errors.append(tag + ': unsupported company')
        status = c.get('status')
        if not member(status, STATUSES):
            errors.append(tag + ': invalid status')
        if not member(c.get('kind'), {'release', 'entitlement', 'leadership', 'other'}):
            errors.append(tag + ': invalid kind')
        if type(c.get('conflict')) is not bool:
            errors.append(tag + ': conflict must be boolean')
        if c.get('conflict') and status != 'unknown':
            errors.append(tag + ': unresolved conflict requires unknown')
        if not isinstance(c.get('limitation'), str):
            errors.append(tag + ': limitation must be text')
        if member(status, {'unknown', 'provisional', 'corroborated'}) and not text_value(c.get('limitation')):
            errors.append(tag + ': limitation required')
        if c.get('kind') == 'entitlement':
            if not member(c.get('access_level'), {'announcement', 'plan', 'account'}):
                errors.append(tag + ': access_level required')
            if c.get('access_level') == 'account' and c.get('account_observed') is not True:
                errors.append(tag + ': account claim requires account_observed true')
        for key in ('absence_claim', 'account_observed'):
            if key in c and type(c[key]) is not bool:
                errors.append(f'{tag}: {key} must be boolean')
        if c.get('absence_claim') is True and not text_list(c.get('checked_channels')):
            errors.append(tag + ': absence claim requires checked_channels')
        if 'event_phase' in c and not member(c['event_phase'], {'announced', 'planned', 'effective'}):
            errors.append(tag + ': invalid event_phase')
        sources = c.get('sources')
        if not isinstance(sources, list):
            errors.append(tag + ': sources must be array'); continue
        eligible = []
        for j, s in enumerate(sources):
            stag = f'{tag}.sources[{j}]'
            if not isinstance(s, dict):
                errors.append(stag + ': object required'); continue
            required = ('url', 'official', 'opened', 'retrieval_at', 'published_at', 'event_at',
                        'date_note', 'locator', 'supports_exact', 'current_scope', 'origin')
            for key in required:
                if key not in s:
                    errors.append(f'{stag}: missing {key}')
            for key in ('official', 'opened', 'supports_exact', 'current_scope'):
                if type(s.get(key)) is not bool:
                    errors.append(f'{stag}: {key} must be boolean')
            try:
                u = urlsplit(s.get('url', ''))
                if u.scheme != 'https' or not u.hostname or u.username or u.password:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                errors.append(stag + ': valid HTTPS URL required')
            if s.get('official') and not official_host(c.get('company'), s.get('url')):
                errors.append(stag + ': official domain mismatch')
            try:
                retrieved = timestamp(s.get('retrieval_at'))
                if retrieved > cutoff:
                    errors.append(stag + ': retrieval after as_of')
            except (ValueError, TypeError):
                errors.append(stag + ': retrieval_at invalid'); retrieved = None
            if not text_value(s.get('locator')) or not text_value(s.get('origin')):
                errors.append(stag + ': locator and origin required')
            if not isinstance(s.get('date_note'), str):
                errors.append(stag + ': date_note must be text')
            for key in ('published_at', 'event_at', 'updated_at', 'crawled_at'):
                value = s.get(key)
                if value is None:
                    if key in ('published_at', 'event_at') and not text_value(s.get('date_note')):
                        errors.append(stag + ': missing date requires date_note')
                    continue
                try:
                    if not isinstance(value, str):
                        raise ValueError('date must be text or null')
                    parsed = date.fromisoformat(value) if len(value) == 10 else timestamp(value)
                    if key in ('published_at', 'updated_at', 'crawled_at') and retrieved is not None:
                        limit = retrieved.date() if type(parsed) is date else retrieved
                        if parsed > limit:
                            errors.append(f'{stag}: {key} after retrieval')
                    if key == 'event_at' and c.get('event_phase') == 'effective' and parsed > (cutoff.date() if isinstance(parsed, date) and not isinstance(parsed, datetime) else cutoff):
                        errors.append(stag + ': future event cannot be effective')
                except (ValueError, TypeError):
                    errors.append(f'{stag}: invalid {key}')
            if s.get('opened') is True and s.get('supports_exact') is True and s.get('current_scope') is True:
                eligible.append(s)
        if status == 'verified' and not any(s.get('official') is True and official_host(c.get('company'), s.get('url')) for s in eligible):
            errors.append(tag + ': verified requires opened exact in-scope official source')
        if status == 'corroborated' and len({s['origin'].strip().casefold() for s in eligible if s.get('official') is False and text_value(s.get('origin'))}) < 2:
            errors.append(tag + ': corroborated requires two declared independent reporting origins')
        if status == 'verified' and any(s.get('published_at') is None for s in eligible):
            warnings.append(tag + ': publication date unknown; do not infer from retrieval date')
    return {'ok': not errors, 'errors': errors, 'warnings': warnings,
            'claims': len(claims), 'verified': sum(c.get('status') == 'verified' for c in claims if isinstance(c, dict)),
            'notice': 'Structural gates only. Semantic support, authenticity and source independence remain reviewer judgments.'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.evidence.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        result = {'ok': False, 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
