// Aula vikar-inspector — paste in DevTools console on https://www.aula.dk/portal/
// Tilpas PROFILE_ID og START herunder, og kør.

(async () => {
  // ===== TILPAS =====
  const PROFILE_ID = 1878975;                                  // barnets instProfileId
  const START = "2024-08-01";                                  // YYYY-MM-DD (skoleårsstart)
  const END   = new Date().toISOString().slice(0, 10);         // i dag
  // ==================

  const csrf = decodeURIComponent(
    (document.cookie.split("; ").find(c => c.startsWith("Csrfp-Token=")) || "").split("=")[1] || ""
  );
  if (!csrf) {
    console.error("Ingen Csrfp-Token cookie fundet — er du logget ind paa www.aula.dk?");
    return;
  }

  // Find aktuel API-version (Aula bumper periodisk; vi prøver fra 22 og opad).
  let apiVersion = null;
  for (let v = 22; v <= 50; v++) {
    const probe = await fetch(`/api/v${v}/?method=profiles.getProfilesByLogin`, { credentials: "include" });
    if (probe.status === 410) continue;
    if (probe.ok) { apiVersion = v; break; }
    console.warn(`API v${v} svarede HTTP ${probe.status}, fortsætter probing...`);
  }
  if (!apiVersion) { console.error("Kunne ikke finde en fungerende API-version mellem v22 og v50."); return; }
  console.log(`Bruger API v${apiVersion}`);

  const fetchRange = async (firstISO, lastISO) => {
    const body = JSON.stringify({
      instProfileIds: [PROFILE_ID],
      resourceIds: [],
      start: `${firstISO} 00:00:00.0000+01:00`,
      end:   `${lastISO} 23:59:59.9990+01:00`,
    });
    const res = await fetch(
      `/api/v${apiVersion}/?method=calendar.getEventsByProfileIdsAndResourceIds`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json, text/plain, */*",
          "Csrfp-Token": csrf,
        },
        body,
      }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${firstISO}..${lastISO}`);
    return res.json();
  };

  const start = new Date(START);
  const end   = new Date(END);
  const cursor = new Date(start.getFullYear(), start.getMonth(), 1);
  const allRows = [];

  while (cursor <= end) {
    const y = cursor.getFullYear();
    const m = cursor.getMonth();
    const first = new Date(y, m, 1);
    const last  = new Date(y, m + 1, 0);
    const fmt = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const firstISO = fmt(first);
    const lastISO  = fmt(last);
    console.log(`Henter ${firstISO}..${lastISO} ...`);
    try {
      const data = await fetchRange(firstISO, lastISO);
      for (const c of (data.data || [])) {
        if (c.type !== "lesson") continue;
        if (c.belongsToProfiles && Number(c.belongsToProfiles[0]) !== Number(PROFILE_ID)) continue;
        const lesson = c.lesson || {};
        const roles = (lesson.participants || []).map(p => p.participantRole);
        allRows.push({
          id: c.id || lesson.id,
          date: (c.startDateTime || "").slice(0, 10),
          title: c.title,
          lessonStatus: lesson.lessonStatus || null,
          roles,
          has_substituteTeacher: roles.includes("substituteTeacher"),
        });
      }
    } catch (e) {
      console.error(e);
    }
    cursor.setMonth(cursor.getMonth() + 1);
  }

  console.log(`\n=== Resultat: ${allRows.length} lektioner ===\n`);

  const counter = arr => arr.reduce((a, x) => (a[x] = (a[x] || 0) + 1, a), {});

  console.log("lessonStatus distribution:");
  console.table(counter(allRows.map(r => r.lessonStatus)));

  console.log("participantRole distribution (alle deltagere):");
  console.table(counter(allRows.flatMap(r => r.roles)));

  const subStatus = allRows.filter(r => r.lessonStatus === "substitute").length;
  const subRole   = allRows.filter(r => r.has_substituteTeacher).length;
  const subBoth   = allRows.filter(r => r.lessonStatus === "substitute" && r.has_substituteTeacher).length;
  console.log("Vikar-tællinger sammenlignet:");
  console.table({
    "lessonStatus == 'substitute'":         subStatus,
    "has substituteTeacher participant":    subRole,
    "begge dele samtidig":                  subBoth,
    "kun lessonStatus":                     subStatus - subBoth,
    "kun substituteTeacher rolle":          subRole - subBoth,
  });

  const onlyStatus = allRows.filter(r => r.lessonStatus === "substitute" && !r.has_substituteTeacher);
  const onlyRole   = allRows.filter(r => r.lessonStatus !== "substitute" && r.has_substituteTeacher);
  if (onlyStatus.length) {
    console.log(`Eksempler: lessonStatus=substitute MEN ingen substituteTeacher (${onlyStatus.length}):`);
    console.table(onlyStatus.slice(0, 5));
  }
  if (onlyRole.length) {
    console.log(`Eksempler: substituteTeacher MEN status != substitute (${onlyRole.length}):`);
    console.table(onlyRole.slice(0, 5));
  }

  const monthly = {};
  for (const r of allRows) {
    const ym = r.date.slice(0, 7);
    if (!monthly[ym]) monthly[ym] = { lessons: 0, lessonStatus_substitute: 0, has_substituteTeacher: 0 };
    monthly[ym].lessons++;
    if (r.lessonStatus === "substitute")  monthly[ym].lessonStatus_substitute++;
    if (r.has_substituteTeacher)          monthly[ym].has_substituteTeacher++;
  }
  console.log("Per måned:");
  console.table(monthly);

  window.aulaInspect = { allRows, monthly };
  console.log("Detaljer ligger i window.aulaInspect.allRows / .monthly");
})();
