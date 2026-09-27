-- Repair the incomplete metadata imported for COURSE-EPG-001.
-- Data-only migration: identifiers, enrollments, progress, attempts and the
-- published version number remain unchanged.

set lock_timeout = '5s';
set statement_timeout = '120s';

do $$
declare
  target_version_id text;
  original_snapshot jsonb;
  repaired_lessons jsonb;
begin
  select course_version_id, content_snapshot_json
    into target_version_id, original_snapshot
  from courseplatform.course_versions
  where course_id = 'COURSE-EPG-001'
    and version_number = 1
    and status = 'PUBLISHED';

  if target_version_id is null then
    return;
  end if;

  insert into courseplatform.migration_reconciliation_issues (
    issue_id,
    migration_key,
    entity_type,
    entity_id,
    issue_code,
    details_json,
    status,
    detected_at,
    resolved_at
  ) values (
    'MRI-20260928120000-COURSE-EPG-001',
    '20260928120000_repair_epg_course_metadata',
    'COURSE_VERSION',
    target_version_id,
    'LEGACY_COURSE_METADATA_REPAIRED',
    jsonb_build_object(
      'courseTitle', (select title from courseplatform.courses where course_id = 'COURSE-EPG-001'),
      'versionTitle', (select title from courseplatform.course_versions where course_version_id = target_version_id),
      'offeringNames', coalesce((
        select jsonb_agg(jsonb_build_object('offeringId', offering_id, 'name', name) order by offering_id)
        from courseplatform.course_offerings
        where course_id = 'COURSE-EPG-001'
      ), '[]'::jsonb),
      'lessons', coalesce((
        select jsonb_agg(to_jsonb(l) order by l.lesson_id)
        from courseplatform.lessons l
        where l.lesson_id in ('LESSON-EAPI-004', 'LESSON-EAPI-005')
      ), '[]'::jsonb),
      'contentSnapshot', original_snapshot
    ),
    'RESOLVED',
    now(),
    now()
  )
  on conflict (issue_id) do nothing;

  update courseplatform.courses
  set title = 'História da Indústria Petrolífera Moçambicana',
      updated_at = now()
  where course_id = 'COURSE-EPG-001'
    and title = 'Historia da industria petrolifera Mocambicana';

  update courseplatform.lessons
  set lesson_number = 1,
      title = 'Fundamentos da Indústria Petrolífera Moçambicana',
      slug = 'fundamentos-industria-petrolifera-mocambicana',
      summary = 'Evolução histórica, cadeia de valor e principais marcos da indústria petrolífera em Moçambique.',
      status = coalesce(nullif(status, ''), 'ACTIVE'),
      updated_at = now()
  where lesson_id = 'LESSON-EAPI-004'
    and course_id = 'COURSE-EPG-001'
    and coalesce(lesson_number, 0) = 0
    and coalesce(btrim(title), '') = '';

  update courseplatform.lessons
  set lesson_number = 2,
      title = 'Exploração, Regulação e Transição Energética',
      slug = 'exploracao-regulacao-transicao-energetica',
      summary = 'Gás natural e GNL, infraestruturas energéticas, regulação, sustentabilidade e transição energética.',
      prerequisite_lesson_id = 'LESSON-EAPI-004',
      status = coalesce(nullif(status, ''), 'ACTIVE'),
      updated_at = now()
  where lesson_id = 'LESSON-EAPI-005'
    and course_id = 'COURSE-EPG-001'
    and coalesce(lesson_number, 0) = 0
    and coalesce(btrim(title), '') = '';

  select coalesce(jsonb_agg(
    case item ->> 'lesson_id'
      when 'LESSON-EAPI-004' then item || jsonb_build_object(
        'lesson_number', 1,
        'title', 'Fundamentos da Indústria Petrolífera Moçambicana',
        'slug', 'fundamentos-industria-petrolifera-mocambicana',
        'summary', 'Evolução histórica, cadeia de valor e principais marcos da indústria petrolífera em Moçambique.',
        'status', coalesce(nullif(item ->> 'status', ''), 'ACTIVE')
      )
      when 'LESSON-EAPI-005' then item || jsonb_build_object(
        'lesson_number', 2,
        'title', 'Exploração, Regulação e Transição Energética',
        'slug', 'exploracao-regulacao-transicao-energetica',
        'summary', 'Gás natural e GNL, infraestruturas energéticas, regulação, sustentabilidade e transição energética.',
        'prerequisite_lesson_id', 'LESSON-EAPI-004',
        'status', coalesce(nullif(item ->> 'status', ''), 'ACTIVE')
      )
      else item
    end
    order by ordinal_position
  ), '[]'::jsonb)
  into repaired_lessons
  from jsonb_array_elements(coalesce(original_snapshot -> 'lessons', '[]'::jsonb))
       with ordinality as snapshot_lesson(item, ordinal_position);

  alter table courseplatform.course_versions
    disable trigger protect_published_course_version;

  update courseplatform.course_versions
  set title = 'História da Indústria Petrolífera Moçambicana',
      content_snapshot_json = jsonb_set(
        jsonb_set(
          original_snapshot,
          '{course,title}',
          to_jsonb('História da Indústria Petrolífera Moçambicana'::text),
          true
        ),
        '{lessons}',
        repaired_lessons,
        true
      ),
      updated_at = now()
  where course_version_id = target_version_id;

  alter table courseplatform.course_versions
    enable trigger protect_published_course_version;

  update courseplatform.course_offerings
  set name = 'História da Indústria Petrolífera Moçambicana - edição inicial',
      updated_at = now()
  where course_id = 'COURSE-EPG-001'
    and name = 'Historia da industria petrolifera Mocambicana - edição inicial';
end
$$;

