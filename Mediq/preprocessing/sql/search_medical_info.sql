-- TVF Creation for extracting relevant information from chunks, tests and images based on user query
CREATE OR REPLACE FUNCTION alloydb_usecase.search_medical_info(
  user_query TEXT,
  embedding_distance_threshold FLOAT DEFAULT 0.3
)
RETURNS TABLE (
  disease_name   TEXT,
  summary_pdf    JSONB,
  summary_csv    JSONB,
  details_chunks JSONB[],
  tests_details  JSONB[],
  related_images JSONB[]
)
LANGUAGE sql
AS $$
WITH qe AS (
  SELECT
    google_ml.embedding('text-embedding-005', user_query)::vector AS embed,
    user_query,
    embedding_distance_threshold
),

best AS (
  SELECT d.*
  FROM alloydb_usecase.disease_info_merged d
  CROSS JOIN qe
  WHERE
      lower(qe.user_query) LIKE '%' || lower(d.disease_name) || '%'
    OR (
         (d.disease_name_embedding <=> qe.embed) IS NOT NULL
         AND (d.disease_name_embedding <=> qe.embed) <= qe.embedding_distance_threshold
       )
),

grouped AS (
  SELECT
    b.disease_name,

    /* --- DETAILS CHUNKS: JSONB[] --- */
    COALESCE(
      ARRAY_AGG(
        jsonb_build_object(
          'chunk_num',  b.chunk_num,
          'chunk_page', b.pages - 30,
          'score',      (b.chunk_embedding <=> qe.embed)
        )
        ORDER BY (b.chunk_embedding <=> qe.embed) ASC NULLS LAST, b.chunk_num
      ) FILTER (WHERE b.chunk_num IS NOT NULL OR b.pages IS NOT NULL),
      ARRAY[]::jsonb[]
    ) AS details_chunks,

    /* Evidence text for AI (compact + aggregated) */
    COALESCE(
      STRING_AGG(
        TRIM(REGEXP_REPLACE(COALESCE(b.chunk_content, ''), '\s+', ' ', 'g')),
        E'\n'
        ORDER BY (b.chunk_embedding <=> qe.embed) ASC NULLS LAST, b.chunk_num
      ) FILTER (WHERE b.chunk_content IS NOT NULL AND b.chunk_content <> ''),
      '(no details)'
    ) AS evidence_text,

    /* Pages list for summary_pdf.pages (distinct pages) */
    COALESCE(
      (
        SELECT jsonb_agg(p ORDER BY p)
        FROM (
          SELECT DISTINCT (b2.pages - 30)::int AS p
          FROM best b2
          WHERE b2.disease_name = b.disease_name
            AND b2.pages IS NOT NULL
        ) p
      ),
      '[]'::jsonb
    ) AS pages_json,

    /* --- TESTS DETAILS: JSONB[] --- */
    COALESCE(
      ARRAY_AGG(
        DISTINCT jsonb_build_object(
          'test_name', b.test_name,
          'score',     (b.disease_name_embedding <=> qe.embed)
        )
      ) FILTER (WHERE b.test_name IS NOT NULL),
      ARRAY[]::jsonb[]
    ) AS tests_details,

    /* Tests text for AI */
    COALESCE(
      ARRAY_TO_STRING(
        ARRAY_AGG(DISTINCT b.test_name ORDER BY b.test_name) FILTER (WHERE b.test_name IS NOT NULL),
        ', '
      ),
      '(no tests)'
    ) AS tests_text,

    /* --- RELATED IMAGES: JSONB[] --- */
    COALESCE(
      ARRAY_AGG(
        DISTINCT jsonb_build_object(
          'caption_text',         b.caption_text,
          'disease_image_base64', b.disease_image_base64,
          'name_distance',        (b.disease_name_embedding <=> qe.embed)
        )
       -- ORDER BY (b.disease_name_embedding <=> qe.embed) ASC NULLS LAST, b.caption_text
      ) FILTER (WHERE b.disease_image_base64 IS NOT NULL),
      ARRAY[]::jsonb[]
    ) AS related_images,


    MAX(
      CASE
        WHEN lower(qe.user_query) LIKE '%' || lower(b.disease_name) || '%'
        THEN 1 ELSE 0
      END
    ) AS name_hit,


    /* score to order diseases (best semantic match wins) */
    MIN(b.disease_name_embedding <=> qe.embed) AS best_score

  FROM best b
  CROSS JOIN qe
  GROUP BY b.disease_name, qe.embed
)

SELECT
  g.disease_name,

  /* PDF SUMMARY (AI) – uses aggregated evidence_text */
  jsonb_build_object(
    'source', 'Medical Encyclopedia PDF Document',
    'summary',
      ai.generate(
      prompt =>
        'User query: "' || qe.user_query || '"' || E'\n' ||
        'TASK: Write a natural-language summary of the disease details using ONLY the evidence provided below.' || E'\n' ||
        'STRICT RULES:' || E'\n' ||
        '1) Use ONLY the text under EVIDENCE. Do NOT use outside medical knowledge. Do NOT guess or add missing facts.' || E'\n' ||
        '2) If EVIDENCE does not contain enough information to answer the query OR If the query is strictly about tests, return NIL.' || E'\n' ||
	'3) The query should either contain only disease names OR it should contain information along with disease names which is present in EVIDENCE' || E'\n' ||
        'EVIDENCE:' || E'\n' ||
        g.evidence_text
    ),'pages', g.pages_json) AS summary_pdf,

  /* CSV SUMMARY (AI) – uses aggregated tests_text */
  jsonb_build_object(
    'source', 'Disease Test Confirmation CSV File',
    'summary',
      ai.generate(
      prompt =>
        'User query: "' || qe.user_query || '"' || E'\n' ||
        'TASK: Write a numbered checklist of diagnostic tests using ONLY the test names provided below.' || E'\n' ||
        'STRICT RULES:' || E'\n' ||
        '1) Use ONLY the text under TEST NAMES. Do NOT use outside medical knowledge. Do NOT guess test purpose, ranges, interpretation, or procedures.' || E'\n' ||
	'2) The query should either contain only disease names OR it should specify medical tests/diagnostic tests/tests along with disease names' || E'\n' ||
        '3) If the query is about disease info other than tests, return NIL.' || E'\n' ||
	'4) Return a numbered checklist of 50 most relevant tests from the list in the order of relevance(highest relevant at the top) with a preface.' || E'\n' ||
        'TEST NAMES:' || E'\n' ||
        g.tests_text
    )) AS summary_csv,

  g.details_chunks,
  g.tests_details,
  g.related_images

FROM grouped g
CROSS JOIN qe
ORDER BY g.name_hit DESC, g.best_score ASC NULLS LAST, g.disease_name;
$$;
