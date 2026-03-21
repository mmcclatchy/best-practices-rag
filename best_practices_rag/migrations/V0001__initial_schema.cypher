CREATE CONSTRAINT constraint_best_practice_id IF NOT EXISTS FOR (n:BestPractice) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT constraint_technology_id IF NOT EXISTS FOR (n:Technology) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT constraint_pattern_id IF NOT EXISTS FOR (n:Pattern) REQUIRE n.id IS UNIQUE;
CREATE INDEX index_best_practice_name IF NOT EXISTS FOR (n:BestPractice) ON (n.name);
CREATE INDEX index_best_practice_category IF NOT EXISTS FOR (n:BestPractice) ON (n.category);
CREATE INDEX index_technology_name IF NOT EXISTS FOR (n:Technology) ON (n.name);
CREATE FULLTEXT INDEX bp_fulltext IF NOT EXISTS FOR (n:__Entity__) ON EACH [n.title, n.body];
