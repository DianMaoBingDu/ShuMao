import sqlite3
import re

def decode_pinyin(s):
    # s is like "ni3 hao3" or "nu:4"
    # Mapping for tones
    tone_marks = {
        'a': 'āáǎàa',
        'e': 'ēéěèe',
        'i': 'īíǐìi',
        'o': 'ōóǒòo',
        'u': 'ūúǔùu',
        'v': 'ǖǘǚǜü',
        'ü': 'ǖǘǚǜü',
    }
    
    words = s.split(' ')
    new_words = []
    
    for word in words:
        if not word: 
            continue
            
        # Detect tone number
        if word[-1].isdigit():
            try:
                tone = int(word[-1])
                base = word[:-1]
            except ValueError:
                tone = 5
                base = word
        else:
            tone = 5
            base = word
            
        # Handle u: -> ü
        base = base.replace('u:', 'ü')
        base = base.replace('U:', 'Ü')
        
        if tone < 1 or tone > 5:
             new_words.append(word)
             continue

        if tone == 5:
            new_words.append(base)
            continue
            
        # Find which vowel to mark
        vowels = 'aeiouvü'
        idx_to_mark = -1
        
        # Check for 'a' or 'e'
        if 'a' in base:
            idx_to_mark = base.find('a')
        elif 'e' in base:
            idx_to_mark = base.find('e')
        elif 'ou' in base:
            idx_to_mark = base.find('o')
        else:
            # Find last vowel
            for i in range(len(base) - 1, -1, -1):
                if base[i].lower() in vowels:
                    idx_to_mark = i
                    break
                    
        if idx_to_mark != -1:
            char = base[idx_to_mark]
            lower_char = char.lower()
            if lower_char in tone_marks:
                # tone 1 is index 0
                replacement = tone_marks[lower_char][tone-1]
                if char.isupper():
                    replacement = replacement.upper()
                
                base = base[:idx_to_mark] + replacement + base[idx_to_mark+1:]
        
        new_words.append(base)
        
    return ' '.join(new_words)

def parse_line(line):
    # Format: Traditional Simplified [pin1 yin1] /glossary 1/glossary 2/
    # Regex to capture the parts
    match = re.match(r'(\S+)\s+(\S+)\s+\[(.*?)\]\s+/(.*)/', line)
    if match:
        traditional = match.group(1)
        simplified = match.group(2)
        pinyin = match.group(3)
        definitions = match.group(4)
        
        # Create normalized pinyin: remove numbers and spaces
        pinyin_clean = re.sub(r'[0-9\s]', '', pinyin).lower()

        # Create numbered pinyin: remove spaces, keep numbers
        # e.g. "ni3 hao3" -> "ni3hao3"
        pinyin_numbered = re.sub(r'\s', '', pinyin).lower()
        
        # Create marked pinyin
        pinyin_marks = decode_pinyin(pinyin)
        
        return traditional, simplified, pinyin, pinyin_clean, pinyin_numbered, pinyin_marks, definitions
    return None

def parse_tatoeba(cursor, filename='en_cn_sentence_pairs.tsv'):
    """Parse Tatoeba sentence pairs and insert into database."""
    print(f"Parsing Tatoeba sentences from {filename}...")
    
    sentences = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            
            # Format: cn_id, chinese, en_id, english
            chinese = parts[1]
            english = parts[3].rstrip('\r\n')  # Remove Windows line ending
            
            sentences.append((chinese, english))
    
    print(f"Inserting {len(sentences)} sentences into database...")
    cursor.executemany('INSERT INTO sentences (chinese, english) VALUES (?, ?)', sentences)
    print("Done parsing Tatoeba sentences.")

def main():
    db_path = 'resources/dictionary.db'
    dict_path = 'resources/cedict_ts.u8'
    tato_filename = 'resources/en_cn_sentence_pairs.tsv'
    hsk_path = 'resources/hsk30.csv'

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute('DROP TABLE IF EXISTS dictionary')
    c.execute('''
        CREATE TABLE dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            traditional TEXT,
            simplified TEXT,
            pinyin TEXT,
            pinyin_clean TEXT,
            pinyin_numbered TEXT,
            pinyin_marks TEXT,
            definitions TEXT,
            has_examples INTEGER DEFAULT 0,
            has_stroke INTEGER DEFAULT 0,
            hsk_level INTEGER DEFAULT 0
        )
    ''')
    
    # We create indices for fast lookups
    c.execute('CREATE INDEX idx_traditional ON dictionary(traditional)')
    c.execute('CREATE INDEX idx_simplified ON dictionary(simplified)')
    c.execute('CREATE INDEX idx_pinyin_clean ON dictionary(pinyin_clean)')
    c.execute('CREATE INDEX idx_pinyin_numbered ON dictionary(pinyin_numbered)')
    c.execute('CREATE INDEX idx_has_examples ON dictionary(has_examples)')
    c.execute('CREATE INDEX idx_hsk_level ON dictionary(hsk_level)')

    print("Reading HSK word list...")
    hsk_map = {}
    try:
        import csv
        with open(hsk_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                level_str = row['Level']
                if '-' in level_str:
                    # Handle ranges like '7-9'
                    level = int(level_str.split('-')[0])
                else:
                    level = int(level_str)
                # Simplified column can contain variants like 爸爸|爸
                words = row['Simplified'].split('|')
                for w in words:
                    # If word already has a level, keep the lower one (easier)
                    if w not in hsk_map or level < hsk_map[w]:
                        hsk_map[w] = level
    except Exception as e:
        print(f"Warning: Could not parse HSK file: {e}")

    print("Reading dictionary file...")
    
    entries = []
    word_to_id = {} # simplified -> index in entries list (excluding headers)
    
    try:
        with open(dict_path, 'r', encoding='utf-8') as f:
            count = 0
            for line in f:
                if line.startswith('#') or line.startswith('%'):
                    continue
                
                parts = parse_line(line.strip())
                if parts:
                    # parts: trad, simp, pinyin, clean, numbered, marks, defs
                    # We add placeholder for has_examples(7), has_stroke(8), hsk_level(9)
                    entry_list = list(parts)
                    
                    # Check if has stroke data (at least one CJK character)
                    simplified = parts[1]
                    has_stroke = 1 if any('\u4e00' <= char <= '\u9fff' for char in simplified) else 0
                    
                    # Get HSK level
                    hsk_level = hsk_map.get(simplified, 0)
                    
                    entry_list.append(0) # has_examples placeholder
                    entry_list.append(has_stroke)
                    entry_list.append(hsk_level)
                    
                    entries.append(entry_list)
                    word_to_id[simplified] = count
                    count += 1

        print(f"Loaded {len(entries)} dictionary entries.")

        # Create sentences table for Tatoeba data
        print("Creating sentences table...")
        c.execute('DROP TABLE IF EXISTS sentences')
        c.execute('''
            CREATE TABLE sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chinese TEXT,
                english TEXT
            )
        ''')
        c.execute('CREATE INDEX idx_sentences_chinese ON sentences(chinese)')
        
        # Parse and insert Tatoeba data
        print(f"Parsing Tatoeba sentences from {tato_filename}...")
        tato_sentences_list = []
        with open(tato_filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line: continue
                parts = line.split('\t')
                if len(parts) < 4: continue
                tato_sentences_list.append((parts[1], parts[3].rstrip('\r\n')))
        
        c.executemany('INSERT INTO sentences (chinese, english) VALUES (?, ?)', tato_sentences_list)
        
        # POPULATE has_examples
        print("Scoring dictionary entries based on example sentence availability...")
        # To be fast, we only check common word lengths (1-4)
        for chinese_sentence, _ in tato_sentences_list:
            # Check all substrings of length 1 to 4
            for i in range(len(chinese_sentence)):
                for length in range(1, 5):
                    if i + length > len(chinese_sentence): break
                    sub = chinese_sentence[i:i+length]
                    if sub in word_to_id:
                        entries[word_to_id[sub]][7] = 1 # Set has_examples = 1

        print("Inserting entries into database...")
        c.executemany('INSERT INTO dictionary (traditional, simplified, pinyin, pinyin_clean, pinyin_numbered, pinyin_marks, definitions, has_examples, has_stroke, hsk_level) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', entries)

        print("Populating FTS index...")
        # Create FTS table for English definitions
        c.execute('DROP TABLE IF EXISTS dictionary_fts')
        c.execute('''
            CREATE VIRTUAL TABLE dictionary_fts USING fts5(
                traditional, simplified, pinyin, definitions,
                content='dictionary',
                content_rowid='id'
            )
        ''')
        c.execute('''
            INSERT INTO dictionary_fts(rowid, traditional, simplified, pinyin, definitions)
            SELECT id, traditional, simplified, pinyin, definitions FROM dictionary
        ''')
        
        conn.commit()
        print("Done!")
        
    except FileNotFoundError:
        print(f"Error: {dict_path} not found.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()
