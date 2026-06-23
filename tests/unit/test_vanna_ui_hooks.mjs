import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const js = fs.readFileSync("webapps/vanna/static/vanna/js/index.js", "utf8");

test("vanna sql test UI exposes allowed profile dropdowns", () => {
  assert.match(js, /const SQL_TEST_PROFILE_OPTIONS = \["ERP_MPC", "ERP_202", "ERP_205", "ERP_209", "ERP_401"\]/);
  assert.match(js, /const SQL_TEST_DEFAULT_PROFILE = "ERP_MPC"/);
  assert.match(js, /id="currentSqlProfileSelect"/);
  assert.match(js, /id="failedSqlProfileSelect"/);
  assert.match(js, /id="adminSqlProfileSelect"/);
});

test("vanna sql test requests include selected profile", () => {
  assert.match(js, /profile: profile,/);
  assert.match(js, /selectedSqlProfile\(profileEl\)/);
});

test("training update requires current sql test pass", () => {
  assert.match(js, /function hasCurrentSqlTestPassed\(formEl, trainingType\)/);
  assert.match(js, /if \(!hasCurrentSqlTestPassed\(formEl, trainingType\)\)/);
  assert.match(js, /markSqlTestPassed\(fieldsEl, sql, profile, Number\.isFinite\(maxRows\) \? maxRows : 10\)/);
  assert.match(js, /fieldsEl\.dataset\.sqlTestSignature === currentSignature/);
});

test("failed query execute button is placed after profile selector", () => {
  const profileIndex = js.indexOf('id="failedSqlProfileSelect"');
  const executeIndex = js.indexOf('執行 QUERY', profileIndex);
  assert.ok(profileIndex > -1);
  assert.ok(executeIndex > profileIndex);
});

test("vanna training metrics switch visible category lists", () => {
  assert.match(js, /loadTrainingDataset\(bubble, true, "failed"\)/);
  assert.match(js, /function showTrainingCategory\(buttonEl, category\)/);
  assert.match(js, /loadTrainingDataset\(bubbleEl, true, normalizedCategory\)/);
  assert.match(js, /function loadTrainingDataset\(bubbleEl, allItems = false, focusCategory = ""\)/);
  assert.match(js, /gridEl\.classList\.toggle\("single-category", normalizedCategory !== "all"\)/);
  assert.match(js, /metricGridEl\.after\(sectionNavEl, sectionGridEl\)/);
  assert.match(js, /data-training-category-target="failed"/);
  assert.match(js, /onclick="showTrainingCategory\(this, 'failed'\)"/);
  assert.match(js, /data-training-category="ddl"/);
  assert.match(js, /data-training-category="documentation"/);
  assert.match(js, /data-training-category="sql"/);
  assert.match(js, /data-training-category="failed"/);
});
