# SI-V2R-BR3 Grammar Validation

## Reference conversion

The pinned reference converter completed without warnings for both schemas:

- SI-V2: `PASS`, 12,761 grammar bytes, 109 rules;
- SI-V2R: `PASS`, 13,907 grammar bytes, 114 rules.

This proves conversion through the reference executable only. It does not prove
that the remote deployment uses the same converter or that every generated rule
has the desired acceptance behavior.

## Provider-free accounting

- Frozen V2R gold objects: `24/24` JSON Schema accepts and `24/24` canonical
  model accepts;
- independent valid domain fixtures: `11/11` JSON Schema and canonical model
  accepts;
- malformed matrix: `11` rows, `9` JSON Schema accepts and `0` canonical model
  accepts;
- grammar acceptance: `NOT_EVALUABLE` because no authenticated matching
  grammar parser/validator was available;
- serialization-order behavior: `NOT_EVALUABLE`.

The six relational and normalization rules remain canonical-runtime checks:
reference target validity, target membership, feature-ID uniqueness, fill target
identity, report-or-section presence, and nonblank collection items. No adapter
or schema projection is inferred from their absence from grammar evidence.
