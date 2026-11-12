-- DROP TABLE IF EXISTS pokemon;
-- TRUNCATE TABLE pokemon;
-- CREATE TABLE pokemon 
-- (
--     Num TEXT,
--     Name TEXT,
--     Type1 TEXT,
--     Type2 TEXT,
--     Height TEXT,
--     Weight TEXT
-- );

SELECT "Name", "Type1", "Weight" 
FROM pokemon 
ORDER BY "Weight" DESC 
LIMIT 5;
