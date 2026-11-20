-- 0010: dining type quiz result ("飲食 MBTI"). Only the 3-letter type is stored, never the answers. Fun + a preference shortcut: it never feeds the engine.
ALTER TABLE product.participant
  ADD COLUMN diet_type TEXT CHECK (diet_type IS NULL OR diet_type ~ '^[AC][RL][WN]$');
