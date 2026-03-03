from flask import Flask, render_template, request, g
import sqlite3
import re
import random
import os
import stanza

app = Flask(__name__)
DATABASE = 'resources/dictionary.db'

# Initialize Stanza locally
stanza_model_dir = os.path.join(os.path.dirname(__file__), 'resources', 'stanza_resources')
if not os.path.exists(stanza_model_dir):
    os.makedirs(stanza_model_dir, exist_ok=True)

# Initialize global pipelines to keep them in memory
print("Loading Stanza pipelines...")
nlp_hans = stanza.Pipeline('zh-hans', model_dir=stanza_model_dir, processors='tokenize,pos', use_gpu=False)
nlp_hant = stanza.Pipeline('zh-hant', model_dir=stanza_model_dir, processors='tokenize,pos', use_gpu=False)
print("Stanza pipelines loaded!")

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

@app.route('/')
def index():
    return render_template('index.html')

def get_example_sentences(characters, limit=5):
    """Get example sentences containing the given characters."""
    sql = '''SELECT chinese, english FROM sentences 
             WHERE chinese LIKE ? 
             LIMIT 50'''
    results = query_db(sql, [f"%{characters}%"])
    if not results:
        return []
    
    sample_size = min(limit, len(results))
    return random.sample(results, sample_size)


@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    RESULTS_PER_PAGE = 20
    
    if not query:
        return render_template('index.html')
    
    # Check if query has digits (tone numbers)
    has_tones = any(char.isdigit() for char in query)
    
    # Normalize query
    clean_query = query.lower().replace(' ', '')
    clean_pinyin_no_tones = re.sub(r'[0-9]', '', clean_query)
    
    db = get_db()
    
    all_results = []
    seen_ids = set()

    def add_unique_results(new_rows, match_type='other'):
        for row in new_rows:
            if row['id'] not in seen_ids:
                result = dict(row)
                result['_match_type'] = match_type  # For scoring
                all_results.append(result)
                seen_ids.add(row['id'])

    # 1. Exact matches (highest priority)
    if has_tones:
        exact_sql = '''
            SELECT *, 1 as has_examples, 1 as has_stroke FROM dictionary 
            WHERE traditional = ? OR simplified = ? OR pinyin_numbered = ?
        '''
        # Note: selecting *, columns will be overridden by the actual values in the table if they exist
        # Since I added them to the table, I should just select *
        exact_sql = 'SELECT * FROM dictionary WHERE traditional = ? OR simplified = ? OR pinyin_numbered = ?'
        exact_rows = query_db(exact_sql, [query, query, clean_query])
    else:
        exact_sql = 'SELECT * FROM dictionary WHERE traditional = ? OR simplified = ? OR pinyin_clean = ?'
        exact_rows = query_db(exact_sql, [query, query, clean_pinyin_no_tones])
    add_unique_results(exact_rows, 'exact')
    
    # Helper for bound index queries (e.g., 'shi' -> 'shj')
    def get_upper_bound(s):
        if not s: return ''
        return s[:-1] + chr(ord(s[-1]) + 1)

    # 2. Starts with
    if has_tones:
        start_sql = '''
            SELECT * FROM dictionary WHERE 
            (traditional >= ? AND traditional < ?) OR 
            (simplified >= ? AND simplified < ?) OR 
            (pinyin_numbered >= ? AND pinyin_numbered < ?) 
            LIMIT 500
        '''
        query_upper = get_upper_bound(query)
        pinyin_upper = get_upper_bound(clean_query)
        start_rows = query_db(start_sql, [query, query_upper, query, query_upper, clean_query, pinyin_upper])
    else:
        start_sql = '''
            SELECT * FROM dictionary WHERE 
            (traditional >= ? AND traditional < ?) OR 
            (simplified >= ? AND simplified < ?) OR 
            (pinyin_clean >= ? AND pinyin_clean < ?) 
            LIMIT 500
        '''
        query_upper = get_upper_bound(query)
        pinyin_upper = get_upper_bound(clean_pinyin_no_tones)
        start_rows = query_db(start_sql, [query, query_upper, query, query_upper, clean_pinyin_no_tones, pinyin_upper])
    add_unique_results(start_rows, 'starts_with')
    
    # 3. English FTS
    fts_sql = '''
        SELECT d.*, f.rank as fts_rank
        FROM dictionary d
        JOIN dictionary_fts f ON d.id = f.rowid
        WHERE dictionary_fts MATCH ? 
        ORDER BY rank 
        LIMIT 500
    '''
    fts_query = f'"{query}"'
    try:
        fts_rows = query_db(fts_sql, [fts_query])
        add_unique_results(fts_rows, 'fts')
    except Exception as e:
        print(f"FTS Error: {e}")
    
    # Merging logic
    merged_results = {}
    for result in all_results:
        # Group by (simplified, pinyin_marks) case-insensitive
        key = (result['simplified'], result['pinyin_marks'].lower())
        
        if key not in merged_results:
            merged_results[key] = result
            # Ensure these are lists/sets for combining
            merged_results[key]['traditional_variants'] = {result['traditional']}
            merged_results[key]['definition_list'] = result['definitions'].split('/')
        else:
            existing = merged_results[key]
            # Merge traditional variants
            existing['traditional_variants'].add(result['traditional'])
            
            # Merge definitions
            new_defs = result['definitions'].split('/')
            for d in new_defs:
                if d and d not in existing['definition_list']:
                    existing['definition_list'].append(d)
            
            # Update data flags (OR logic)
            existing['has_examples'] = existing.get('has_examples', 0) or result.get('has_examples', 0)
            existing['has_stroke'] = existing.get('has_stroke', 0) or result.get('has_stroke', 0)
            
            # Update HSK level (take the lower/easier one if both exist)
            l1 = existing.get('hsk_level', 0)
            l2 = result.get('hsk_level', 0)
            if l1 == 0: existing['hsk_level'] = l2
            elif l2 != 0: existing['hsk_level'] = min(l1, l2)
            
            # Use the higher priority match type
            priority_map = {'exact': 0, 'starts_with': 1, 'fts': 2, 'other': 3}
            if priority_map[result.get('_match_type', 'other')] < priority_map[existing.get('_match_type', 'other')]:
                existing['_match_type'] = result['_match_type']
                # If the better match type has a rank, use it
                if 'fts_rank' in result:
                    existing['fts_rank'] = result['fts_rank']

    # Convert back to list and finalize merged fields
    all_results = []
    for entry in merged_results.values():
        # Join traditional variants back into a string
        entry['traditional'] = " / ".join(sorted(list(entry['traditional_variants'])))
        # Join definitions back into the canonical format
        entry['definitions'] = "/".join(entry['definition_list'])
        all_results.append(entry)

    # Score and sort results
    def score_result(result):
        match_type = result.get('_match_type', 'other')
        
        # Priority (lower = better)
        priority_map = {
            'exact': 0,
            'starts_with': 1,
            'fts': 2,
            'other': 3
        }
        priority = priority_map.get(match_type, 3)
        
        # Data Quality Bonus (lower = better)
        data_score = 0
        if not result.get('has_examples'): data_score += 2
        if not result.get('has_stroke'): data_score += 5 # No stroke data is a big penalty
        
        # HSK Score (lower = better)
        # HSK levels 1-7 (7 is 7-9). If not in HSK, give level 10 as penalty
        hsk_level = result.get('hsk_level', 0)
        hsk_score = hsk_level if hsk_level > 0 else 10
        
        # FTS Rank (for English searches)
        fts_rank = result.get('fts_rank', 0)
        
        # Length (shorter = better, prefer common words)
        length = len(result.get('simplified', ''))
        
        # Bonus if the query exactly matches one of the definitions (split by /)
        exact_def_bonus = 0
        if match_type == 'fts':
            defs = result.get('definitions', '').lower().split('/')
            if query.lower() in [d.strip() for d in defs]:
                exact_def_bonus = -10 # Big bonus for exact definition match
        
        return (priority, exact_def_bonus, hsk_score, data_score, fts_rank, length)
    
    all_results.sort(key=score_result)
    
    # Pagination
    total_results = len(all_results)
    total_pages = (total_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE  # Ceiling division
    start_idx = (page - 1) * RESULTS_PER_PAGE
    end_idx = start_idx + RESULTS_PER_PAGE
    paginated_results = all_results[start_idx:end_idx]
    
    prefetched_chars = {}
    chars_to_fetch = set()
    for result in paginated_results:
        if len(result['simplified']) >= 2:
            for char in result['simplified']:
                chars_to_fetch.add(char)
                
    if chars_to_fetch:
        placeholders = ','.join(['?'] * len(chars_to_fetch))
        char_rows = query_db(f'SELECT * FROM dictionary WHERE simplified IN ({placeholders}) AND length(simplified) = 1', list(chars_to_fetch))
        for row in char_rows:
            char = row['simplified']
            if char not in prefetched_chars:
                prefetched_chars[char] = []
            prefetched_chars[char].append(row)

    # Get example sentences and character breakdown for each result
    char_cache = {}
    for result in paginated_results:
        char_to_search = result['simplified']
        
        # 1. Examples
        examples = get_example_sentences(char_to_search, limit=3)
        result['examples'] = [dict(ex) for ex in examples]
        
        # 2. Character Breakdown (for words with 2+ characters)
        result['character_breakdown'] = []
        if len(char_to_search) >= 2:
            # We want to breakdown both simplified and traditional if they differ
            # But the breakdown is usually per character slot
            # So we iterate through the simplified characters
            for i, char in enumerate(char_to_search):
                if char in char_cache:
                    result['character_breakdown'].append(char_cache[char])
                else:
                    # Fetch ALL definitions for this specific character from pre-fetched data
                    char_rows = prefetched_chars.get(char, [])
                    
                    if char_rows:
                        # Aggregate data from multiple entries (homographs) and GROUP BY PINYIN
                        groups = {} # pinyin -> {'definitions': [], 'traditional': set()}
                        
                        # Use the first row as the base template
                        char_info = dict(char_rows[0])
                        
                        for row in char_rows:
                            pinyin = row['pinyin_marks']
                            if not pinyin: pinyin = "Unknown"
                            
                            if pinyin not in groups:
                                groups[pinyin] = {'definitions': [], 'traditional': set()}
                            
                            # Definitions
                            defs = row['definitions'].split('/')
                            for d in defs:
                                if d and d not in groups[pinyin]['definitions']:
                                    groups[pinyin]['definitions'].append(d)
                                    
                            # Traditional
                            groups[pinyin]['traditional'].add(row['traditional'])
                        
                        # Convert groups to list for template
                        grouped_entries = []
                        for pin, data in groups.items():
                            grouped_entries.append({
                                'pinyin': pin,
                                'definitions': data['definitions'],
                                'traditional': sorted(list(data['traditional']))
                            })
                        
                        # Sort by pinyin
                        grouped_entries.sort(key=lambda x: x['pinyin'])
                        
                        char_info['grouped_entries'] = grouped_entries
                        
                        # Legacy fields for backward compatibility / fallback
                        char_info['pinyin_marks'] = " / ".join([g['pinyin'] for g in grouped_entries])
                        all_defs = [d for g in grouped_entries for d in g['definitions']]
                        char_info['short_definitions'] = "/".join(all_defs[:4])
                        
                        char_cache[char] = char_info
                        result['character_breakdown'].append(char_info)
                    else:
                        # Fallback for characters not found as single entries
                        result['character_breakdown'].append({
                            'simplified': char, 
                            'traditional': char, 
                            'pinyin_marks': '', 
                            'definitions': 'N/A',
                            'short_definitions': 'N/A'
                        })

        # Remove internal scoring field
        result.pop('_match_type', None)
    
    return render_template('results.html', 
                         query=query,
                         results=paginated_results,
                         page=page,
                         total_pages=total_pages,
                         total_results=total_results,
                         results_per_page=RESULTS_PER_PAGE)

POS_MAPPING = {
    'ADJ': 'Adjective',
    'ADP': 'Adposition',
    'ADV': 'Adverb',
    'AUX': 'Auxiliary',
    'CCONJ': 'Conjunction',
    'DET': 'Determiner',
    'INTJ': 'Interjection',
    'NOUN': 'Noun',
    'NUM': 'Numeral',
    'PART': 'Particle',
    'PRON': 'Pronoun',
    'PROPN': 'Proper Noun',
    'PUNCT': 'Punctuation',
    'SCONJ': 'Conjunction',
    'SYM': 'Symbol',
    'VERB': 'Verb',
    'X': 'Other',
    'Space': 'Space'
}

@app.route('/analyze')
def analyze():
    
    # Check if 'text' parameter exists in the URL
    if 'text' in request.args:
        text = request.args.get('text', '').strip()
        model = request.args.get('model', 'hans').strip()
        # If text is empty (user submitted empty form), use default
        if not text:
            text = "我喜欢可爱的猫"
    else:
        # Initial page load without query param
        text = ""
        model = "hans"
    
    if not text:
        return render_template('analyze.html', analyzed_segments=[], model=model)
    
    # Process text with Stanza using correct model
    if model == 'hant':
        doc = nlp_hant(text)
    else:
        doc = nlp_hans(text)
    
    analyzed_segments = []
    
    db = get_db()
    
    for sentence in doc.sentences:
        for word_obj in sentence.words:
            word = word_obj.text
            flag = word_obj.upos  # Universal POS tag
            # Get human readable POS tag
            human_pos = POS_MAPPING.get(flag, flag)

            # Skip purely whitespace segments if you want, or keep them for formatting
            if not word.strip():
                analyzed_segments.append({
                    'word': word,
                    'pos': 'Space',
                    'definitions': None
                })
                continue
                
            # Query dictionary for this word
            # We fetch ALL matches to handle homographs
            rows = query_db('SELECT * FROM dictionary WHERE simplified = ? OR traditional = ?', [word, word])
            
            segment_data = {
                'word': word,
                'pos': flag,
                'human_pos': human_pos,
                'pinyin': '',
                'definitions': '',
                'hsk_level': 0
            }
            
            if rows:
                groups = {}
                min_hsk = 100 
                
                for row in rows:
                    pinyin = row['pinyin_marks']
                    if not pinyin: pinyin = "Unknown"
                    
                    if pinyin not in groups:
                        groups[pinyin] = {'definitions': []}
                    
                    defs = row['definitions'].split('/')
                    for d in defs:
                        if d and d not in groups[pinyin]['definitions']:
                            groups[pinyin]['definitions'].append(d)
                    
                    hsk = row['hsk_level']
                    if hsk > 0 and hsk < min_hsk:
                        min_hsk = hsk
                
                # Convert to sorted list
                grouped_entries = []
                for pin, data in groups.items():
                    grouped_entries.append({
                        'pinyin': pin,
                        'definitions': data['definitions']
                    })
                grouped_entries.sort(key=lambda x: x['pinyin'])
                
                segment_data['grouped_entries'] = grouped_entries
                
                # Backwards compatibility
                segment_data['pinyin'] = " / ".join([g['pinyin'] for g in grouped_entries])
                all_defs = [d for g in grouped_entries for d in g['definitions']]
                segment_data['definitions'] = "/".join(all_defs)
                segment_data['hsk_level'] = min_hsk if min_hsk != 100 else 0
            else:
                # Fallback: maybe it's punctuation or a name not in dict
                pass
                
            analyzed_segments.append(segment_data)
        
    return render_template('analyze.html', text=text, analyzed_segments=analyzed_segments, model=model)
