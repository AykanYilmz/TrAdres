# Proje: Türkçe Adres Ayrıştırıcı (açık kaynak Python kütüphanesi + CLI + API)

> Bu dosya projenin ana talimatıdır. Her oturumun başında bunu oku, en alttaki **İlerleme** bölümünden kaldığımız yeri bul ve oradan devam et.

## 0. Rolün ve çalışma şeklimiz

Sen deneyimli bir Python kütüphane geliştiricisi ve açık kaynak bakımcısısın. Ben (Aykan) junior bir yazılım geliştiriciyim; bu proje hem portfolyom hem de gerçekten kullanılacak bir açık kaynak araç olacak. **Amacım sadece çalışan kod değil, her kararı mülakatta anlatabilecek kadar anlamak.**

Kurallar:
1. **Fazlar halinde ilerle.** Her fazın sonunda dur, ne yaptığını ve neden öyle yaptığını 5–10 maddede özetle, benim onayımı bekle. Bir sonraki faza kendiliğinden geçme.
2. **Büyük kararlarda önce seçenekleri sun** (kütüphane seçimi, veri kaynağı, API tasarımı, isimlendirme): 2–3 seçenek, artı/eksi, senin önerin. Ben seçeyim.
3. **Öğret:** Yeni bir kavram kullandığında (ör. trie, fuzzy matching, property-based test, trusted publishing) bir iki cümleyle ne olduğunu ve neden gerektiğini açıkla.
4. **Bana görev bırakma.** Tüm kodu ve testleri sen yaz; ben açıkça istemedikçe "senin görevin" diye iş bırakma.
5. **Ölçmeden özellik ekleme.** Doğruluğu artırdığını iddia ettiğin her değişikliği değerlendirme setinde (Faz 3) ölç, önce/sonra sayılarını göster.
6. **Bağımlılıkları az tut.** Her yeni bağımlılığı gerekçelendir. Çekirdek kütüphane mümkünse sadece `rapidfuzz` gibi küçük bir bağımlılıkla çalışsın; API, CLI ve demo `extras` olarak gelsin.
7. Commit'ler küçük ve **Conventional Commits** formatında olsun (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). Her commit'te testler geçsin.
8. Emin olmadığın bir bilgiyi (veri lisansı, bir kütüphanenin güncel API'si, PyPI'da isim müsaitliği) uydurma; kontrol et ya da bana sor.

## 1. Problem

Türkiye'de adresler serbest metin olarak yazılıyor ve son derece dağınık:

```
Atatürk Mah. 23 Nisan Cad. No:5/3 Merkez/Bolu
ataturk mh 23nisan cd no 5 d 3 bolu merkez
Çankaya Ankara Kızılay Mahallesi Gazi Mustafa Kemal Blv. No: 12 Kat: 4 Daire: 8
CANKAYA/ANKARA kizilay mah gmk bulvarı 12/8
Yenimahalle Ankara, Batıkent, 1923. Cadde, Toki Konutları B-3 Blok, No:7, D:14
```

E-ticaret, kargo, CRM ve lojistik yazan her ekip bu adresleri parçalamak, doğrulamak ve standart biçime getirmek zorunda. Bu kütüphane bunu yapacak:

```python
from tradres import parse

result = parse("ataturk mh 23nisan cd no 5 d 3 bolu merkez")
result.il            # "Bolu"
result.ilce          # "Merkez"
result.mahalle       # "Atatürk"
result.cadde         # "23 Nisan"
result.bina_no       # "5"
result.daire         # "3"
result.confidence    # 0.0–1.0 arası genel güven skoru
result.format()      # "Atatürk Mah. 23 Nisan Cad. No:5 D:3 Merkez/Bolu"
result.to_dict()     # JSON'a hazır sözlük, her alanın kendi güven skoruyla
```

## 2. Kapsam

### v0.1 (ilk yayın) — olmazsa olmazlar
- **Normalizasyon**
  - Türkçe'ye doğru büyük/küçük harf dönüşümü (Python'un `str.lower()`'ı `I → i` yapar, Türkçe'de `I → ı`, `İ → i` olmalı). Kendi `tr_lower` / `tr_upper` fonksiyonlarımız olsun ve testleri bulunsun.
  - ASCII'ye çevrilmiş girdiyi tanıma: `cankaya` → `Çankaya`, `sisli` → `Şişli` (eşleştirme Türkçe karakterlerden bağımsız bir anahtar üzerinden yapılsın, çıktı her zaman doğru Türkçe yazımla dönsün).
  - Kısaltmalar: `Mah./Mh./Mahallesi`, `Cad./Cd./Caddesi`, `Sok./Sk./Sokağı`, `Blv./Bulvarı`, `Apt./Apartmanı`, `Sit./Sitesi`, `Bl./Blok`, `No:/No`, `D:/Daire`, `K:/Kat` vb. Bu liste kodun içine gömülmesin, ayrı bir veri dosyasında dursun ki katkıcılar kolayca eklesin.
  - Boşluk, noktalama ve birleşik yazım temizliği (`23nisan` → `23 Nisan`, `No:5/3` → bina 5, daire 3).
- **Bileşen çıkarma:** il, ilçe, mahalle, cadde, sokak, bulvar, site, bina adı, blok, bina no, kat, daire, posta kodu, tarif ("okul yanı" gibi yön tarifleri). Tanınamayan kısım `kalan` (unparsed) alanına konsun, asla sessizce atılmasın.
- **Gazetteer (resmi yer adları) ile doğrulama:** il → ilçe → mahalle hiyerarşisi. Bir ilçe yanlış ile eşleşirse güven düşsün; il yazılmamışsa ilçeden çıkarılabiliyorsa (tek bir ile aitse) doldurulsun ve bu durum işaretlensin.
- **Bulanık eşleştirme:** Yazım hatalarını tolere et (`Kızılay` / `Kizilay` / `Kzılay`). Eşik değerleri sabit kodlanmasın, ayarlanabilir olsun.
- **Sıra bağımsızlığı:** `Merkez/Bolu`, `Bolu Merkez`, `Bolu - Merkez`, adresin başında ya da sonunda il/ilçe.
- **Güven skoru:** Her alan için ve genel olarak. Nasıl hesaplandığı README'de açıklansın.
- **Standart biçimlendirme:** `result.format()` tek, tutarlı bir yazım üretsin.
- **CLI:** `tradres parse "adres"` (JSON çıktı) ve `tradres parse-csv girdi.csv --column adres -o cikti.csv` (toplu işleme, ilerleme çubuğu).
- **Tip güvenliği:** Tüm public API tip ipuçlu, `py.typed` dosyası olan, `mypy --strict` ile temiz.

### v0.2 ve sonrası (şimdi yapma, yol haritasına yaz)
- FastAPI servisi + Docker image (tekli ve toplu `/parse` uç noktaları)
- Hugging Face Spaces'te (Gradio) canlı demo
- Posta kodu tahmini ve doğrulaması
- Belirsiz adreslerde birden fazla aday döndürme (`parse_candidates`)
- Değerlendirme seti kural tabanlı yaklaşımda tıkanırsa küçük bir NER modeli denemek (önce ölç, sonra karar ver)

### Kapsam dışı
- Coğrafi koordinat (geocoding) — harici servis gerektirir
- Gerçek kişilere ait adres verisi toplamak

## 3. Veri

- İl/ilçe/mahalle listesi için **lisansı açık ve güncel** bir kaynak bul. Seçenekleri (resmi kurumların yayınladığı listeler, açık topluluk veri setleri) lisansları, güncellikleri ve kapsamlarıyla birlikte bana sun; ben seçeyim. İzin vermeyen bir siteyi kazıma.
- Ham veriyi işleyip pakete gömülecek kompakt bir biçime (ör. sıkıştırılmış JSON) dönüştüren bir **build script'i** yaz (`scripts/build_gazetteer.py`). Paketin içindeki veri bu script'le yeniden üretilebilir olsun.
- Verinin kaynağını, lisansını ve tarihini `DATA_SOURCES.md` dosyasında belgele.
- Paket kurulumunda internet gerekmesin; veri paketle gelsin. Paket boyutunu ölç ve README'ye yaz.
- Gazetteer bir kez yüklensin (lazy loading + cache), arama için uygun bir indeks kullanılsın (ör. ASCII anahtarlı sözlük, gerekirse trie). Hangisini neden seçtiğini açıkla.

## 4. Mimari

`src/` düzeni kullan. Önerilen modüller (gerekirse değiştir ama gerekçelendir):

```
src/tradres/
├── __init__.py          # public API: parse, normalize, Address
├── models.py            # Address dataclass'ı / alanlar, güven skorları, to_dict, format
├── normalization.py     # Türkçe harf dönüşümü, ASCII anahtar, temizlik
├── abbreviations.py     # kısaltma sözlüğünü yükleyen kod (veri ayrı dosyada)
├── tokenizer.py         # adresi anlamlı parçalara bölme
├── extractors/          # her bileşen için ayrı çıkarıcı (numara, sokak, mahalle, il/ilçe...)
├── gazetteer.py         # yer adı verisi, indeks, hiyerarşi doğrulaması
├── matching.py          # bulanık eşleştirme, eşikler
├── scoring.py           # güven skoru hesaplama
├── parser.py            # her şeyi birleştiren pipeline
├── cli.py               # komut satırı arayüzü
├── data/                # gömülü gazetteer ve kısaltma dosyaları
└── py.typed
```

Pipeline: `ham metin → normalize → tokenize → sayısal alanlar (no/kat/daire/posta kodu) → yer adları (gazetteer + fuzzy) → sokak/cadde/site/blok → hiyerarşi doğrulama → skorlama → Address`.

Her aşama saf (pure) fonksiyon olsun, ayrı ayrı test edilebilsin.

## 5. Kalite

- **Testler:** `pytest`. Her modülün birim testleri + uçtan uca testler.
- **Property-based test:** `hypothesis` ile ör. "normalize iki kez uygulanınca sonuç değişmez", "parse asla exception fırlatmaz, en kötü ihtimalle boş alanlar döner", "format edilen adres tekrar parse edilince aynı alanlar çıkar".
- **Değerlendirme seti (çok önemli):** `eval/` klasöründe, elle etiketlenmiş en az 300 adres (YAML/JSON: girdi → beklenen alanlar). Farklı yazım tarzları, hatalar, eksik bilgiler, farklı iller içersin. **Gerçek kişilere ait adres kullanma (KVKK);** gerçek yer adlarıyla uydurma bina/daire numaraları kullan.
- **Değerlendirme script'i:** `python -m eval` alan bazında precision / recall / F1 ve tam doğru adres oranı raporlasın. Sonuç README'deki tabloya girsin ve CI'da belirli bir eşiğin altına düşerse build kırılsın.
- **Performans:** Adres başına süreyi ve 10.000 adreslik toplu işlemeyi ölçen bir benchmark (`pytest-benchmark`). Hedef değeri ilk ölçümden sonra birlikte belirleyelim.
- **Araçlar:** `uv` (paket ve ortam yönetimi), `ruff` (lint + format), `mypy --strict`, `pre-commit`.
- Test kapsamı %90'ın altına düşerse CI başarısız olsun.

## 6. Açık kaynak altyapısı

- `LICENSE` (MIT), `README.md` (İngilizce, ana dosya), `README.tr.md` (Türkçe), `CHANGELOG.md` (Keep a Changelog), `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`.
- `CONTRIBUTING.md` özellikle şunları anlatsın: yeni kısaltma nasıl eklenir, yanlış ayrıştırılan adres nasıl değerlendirme setine eklenir, testler nasıl çalıştırılır.
- Issue şablonları: **"Yanlış ayrıştırılan adres"** (girdi, beklenen, gerçekleşen; "gerçek kişisel adres paylaşmayın, numaraları değiştirin" uyarısıyla), hata bildirimi, özellik isteği. PR şablonu.
- İlk katkıcılar için 5–10 tane `good first issue` önerisi hazırla (ör. eksik kısaltmalar).
- **GitHub Actions:**
  - `ci.yml`: Python 3.10–3.13 matrisi; ruff, mypy, pytest + kapsam, değerlendirme eşiği.
  - `release.yml`: `v*` tag'i atılınca build + PyPI'a **Trusted Publishing** (OIDC, token saklamadan) ile yayın + GitHub Release notları.
- Dependabot ve sürüm numaralandırma için Semantic Versioning.
- README rozetleri: CI, kapsam, PyPI sürümü, Python sürümleri, lisans.

## 7. README (yıldız getiren kısım)

İngilizce README şu sırayla olsun:
1. Tek cümlelik açıklama + rozetler
2. **Önce/sonra örneği** (dağınık adres → düzgün JSON) ve bir **GIF** (CLI kullanımı)
3. `pip install` ve 5 satırlık kullanım örneği
4. Özellikler listesi
5. Doğruluk tablosu (değerlendirme setinden, alan bazında) ve performans sayıları
6. Nasıl çalışır (kısa pipeline şeması, Mermaid)
7. CLI kullanımı, Yol haritası, Katkı, Veri kaynakları ve lisans

İngilizcem B1 seviyesinde; README'yi sade ve doğal bir İngilizceyle yaz, sonra Türkçe versiyonunu oluştur.

## 8. Fazlar

Her faz sonunda dur ve onayımı bekle.

- **Faz 0 — İsim ve iskelet:** 5 isim öner (kısa, akılda kalan, PyPI'da ve GitHub'da müsait mi kontrol et). Ben seçince: `uv` ile proje, `src/` düzeni, pyproject, ruff, mypy, pytest, pre-commit, LICENSE, boş README, ilk CI. Paket adı (`import tradres`) ve CLI adı (`tradres`) bu dosyada güncellendi.
- **Faz 1 — Normalizasyon:** Türkçe harf dönüşümü, ASCII anahtar, kısaltma sözlüğü, temizlik + kapsamlı testler (hypothesis dahil).
- **Faz 2 — Veri:** Veri kaynağı seçenekleri → seçim → build script'i → gazetteer modülü ve indeks → `DATA_SOURCES.md`.
- **Faz 3 — Değerlendirme seti:** Önce etiketleme formatı ve ilk 50 adres, sonra script, sonra 300'e tamamlama. **Parser'dan önce yapıyoruz ki her adımı ölçebilelim.**
- **Faz 4 — Parser v1:** Tokenizer, sayısal alanlar, yer adları, sokak/cadde; ilk değerlendirme sonuçları. Sonunda basit yerel web demosu (`python -m demo`): üstte adres kutusu, altta ayrıştırılmış hali.
- **Faz 5 — İyileştirme:** Bulanık eşleştirme, sıra bağımsızlığı, hiyerarşi doğrulama, güven skoru. Her değişikliğin önce/sonra skorları.
- **Faz 6 — CLI ve API yüzeyi:** CLI komutları, `format()`, `to_dict()`, public API'nin son hali, docstring'ler.
- **Faz 7 — Açık kaynak altyapısı:** Bölüm 6'nın tamamı, release workflow, TestPyPI'a deneme yayını.
- **Faz 8 — README ve v0.1.0:** README (EN + TR), GIF için senaryo, benchmark sonuçları, CHANGELOG, `v0.1.0` tag'i ve PyPI yayını.
- **Faz 9 — Tanıtım:** Paylaşım metinleri taslakları (LinkedIn, Twitter/X, Reddit r/Python, Hacker News "Show HN", Türk geliştirici toplulukları) ve hangi kanalda nasıl paylaşılacağına dair öneriler.

## 9. İlerleme

> Her faz bittiğinde bu bölümü güncelle: ne yapıldı, alınan önemli kararlar ve nedenleri, değerlendirme skorları, açık sorular.

- [x] Faz 0 — İsim ve iskelet (2026-11-04)
  - İsim: **TrAdres** → PyPI dağıtım adı `tradres` (kontrol: 2026-11-04, PyPI'da boştu), import adı `tradres`, CLI `tradres`. GitHub: `AykanYilmz/TrAdres`.
  - uv 0.13.7, hatchling build backend, `src/` düzeni, `requires-python >=3.10`, çekirdekte bağımlılık yok.
  - Dev araçları (dependency group `dev`): pytest, pytest-cov, hypothesis, mypy, ruff, pre-commit.
  - CI: lint işi (ruff check + format, mypy --strict) + 3.10–3.13 test matrisi, kapsam eşiği %90 (pyproject'te `fail_under`).
- [x] Faz 1 — Normalizasyon (2026-11-04, onaylandı)
  - `normalization.py`: `tr_lower`, `tr_upper`, `tr_title`, `ascii_key`, `clean`, `normalize` (top-level `tradres.normalize`).
  - `abbreviations.py` + `data/abbreviations.json`: 11 tür (mahalle … posta_kodu), `lookup()`, veri doğrulaması.
  - 173 test (örnek + doctest + hypothesis), kapsam %98.6. `HYPOTHESIS_PROFILE=thorough` ile 5000 örnekte de temiz.
  - `apartman` türü Address'te `bina_adi` alanına gidecek (Faz 3'te Aykan seçti).
- [x] Faz 2 — Veri (2026-11-04, onaylandı)
  - Kaynak: **Wikidata (CC0)**, seçenekler (Wikidata / turkiye-api / OSM) sunuldu, Aykan seçti.
  - `scripts/build_gazetteer.py` + `scripts/gazetteer_corrections.json` → `src/tradres/data/gazetteer.json.gz` (194 KiB, deterministik).
  - Sonuç: 81 il, 973 ilçe (resmi listeyle birebir), 46.112 mahalle/köy (resmi isimlerin ~%88.6'sı aynı ilçede bulunuyor).
  - `gazetteer.py`: `load_gazetteer()` (lazy + cache), `find_il/find_ilce/find_mahalle/provinces_of_district`, ilk yükleme ~0.3 s.
  - Wheel 206 KiB. 268 test, kapsam %98.6. `DATA_SOURCES.md` yazıldı.
  - Açık soru: eksik ~%11 mahallenin doğruluğa etkisi Faz 3'te ölçülecek; gerekirse Wikidata'ya katkı / ek dosya.
- [x] Faz 3 — Değerlendirme seti (2026-11-05, onaylandı)
  - `eval/addresses/*.yaml`: elle etiketlenmiş 313 adres, 20 etiket, 69 il. `python -m eval` (`--parser`, `--failures`, `--tag`, `--markdown`, `--check`, `--min-f1`, `--min-exact`).
  - Baseline (`eval/baseline.py`): F1 0.881, tam doğru %47.0. Parser v1 bunu geçmeli. Set beklenenden kolay: katkılarla zorlaştırılmalı.
  - Set gazetteer'dan bağımsız örneklendi: 43 adres `gazetteer_disi` (%13.7), 1 adres `gazetteer_yazim_farki`.
  - CI eşiği henüz yok; parser gelince Faz 4'te `--min-f1` / `--min-exact` ile eklenecek.
  - Açık soru: 144 mahallede Wikidata yazımı resmiyle farklı (çoğu biçim farkı); mahalle düzeltmesi Faz 5'te ele alınacak.
- [x] Faz 4 — Parser v1 (2026-11-05, onaylandı)
  - `models.py` (`Address`, `FIELDS`), `tokenizer.py`, `extractors/{numbers,places,streets}.py`, `parser.py`; `tradres.parse` public.
  - İlk ölçüm: **F1 0.977, tam doğru %88.8** (278/313). Güncel baseline: F1 0.890, %53.0. Aşamalar: sayılar %0.6 → yer adları %2.6 → cadde/sokak %80.8 → tam pipeline %88.8. Hız ~174 µs/adres.
  - **Bu sayı iyimser:** seti ve parser'ı aynı kişi (Claude) yazdı, kurallar setin örüntülerini biliyordu. Faz 5'ten önce ayrı bir test bölümü önerildi.
  - CI eşiği: `python -m eval --min-f1 0.95 --min-exact 0.85`.
  - Yerel demo: `python -m demo` → http://127.0.0.1:8000. Sadece stdlib, sadece localhost, adres kaydetmez. Pakete dahil değil.
  - Faz 5'e kalanlar: yazım hatası (`yazim_hatasi` %27.3), ASCII cadde/sokak adlarının Türkçeleştirilmesi, mahalleden ilçe çıkarımı, `İst.`/`Ş.Urfa`/`G.Antep` kısa adları, `gmk`.
  - Demoda bulunan hata düzeltildi: tarif sözcükleri (`üzeri`, `yanı`, `lojmanları`...) bina adına karışıyordu. Önce F1 0.977, %88.8 (278/313) → sonra **F1 0.979, %89.5 (280/313)**; `bina_adi` F1 0.815 → 0.963.
- [x] Faz 5 — İyileştirme (2026-11-05, onaylandı)
  - Önce kilitli test seti: `eval/holdout/test.yaml`, 100 adres, 48 il, geliştirme setiyle ortak mahalle yok. `python -m eval --holdout` sadece toplamları gösterir.
  - **Kilitli test seti: F1 0.966 → 0.975, tam doğru %82.0 → %89.0** (baseline F1 0.824, %38.0). Geliştirme seti: F1 0.979 → 0.996, 283/316 → 312/318 (%98.1). İkisi arasındaki fark ezberin ölçüsü: README'de kilitli test sayısı kullanılacak.
  - Adımlar (geliştirme seti, tam doğru): `Daire No` 283/316 → bulanık eşleştirme 297 → Türkçe harf + kısa adlar 303 → çıkarım, hiyerarşi, lojman, kapı no 310/318 → gevşek mahalle 312/318.
  - Yeni: `matching.py` (`MatchConfig`, OSA), `scoring.py` (`Origin`, `score_address`), `Gazetteer.fuzzy_*`/`respell`, `data/name_words.json`. `parse(text, config=...)`, `Address.confidence`, `Address.field_confidence`. Demo güven gösteriyor.
  - Hız ~222 µs/adres (önce ~174), wheel 228 KiB, rapidfuzz ilk çekirdek bağımlılık. CI eşiği `--min-f1 0.98 --min-exact 0.95`.
  - Sızıntı: test setinin ilk ölçümünde etiket grupları ekrana geldi, sonra kapatıldı; `İç Kapı No` kuralı test setindeki bir adresten önce biliniyordu ve geliştirme setine de eklendi. Test seti aynı kişi tarafından yazıldı. v0.1 öncesi yeni adreslerle tazelenmeli.
  - Güven skoru açıklanabilir ama kalibre değil: yanlış adreslerin ortalaması 0.859, doğruların 0.934; geliştirme setinde hata az olduğu için eşik önerilemiyor.
  - Faz 5 özetinden sonra Aykan'ın demoda bulduğu hatalar: `tarif` alanı v0.2'den öne alındı (`data/description_words.json`), `D:6/B`, iki kez yazılan il/ilçe, virgüller arası anahtarsız site adı (güven düşük). Aykan Faz 5'i henüz onaylamadı.
  - Veri (A seçeneği): `scripts/gazetteer_additions.json`, kaynaklı tek tek girdiler (`Fırat`, `Kuşdilli`); gereksiz kalan girdi derlemeyi kırar. Wikidata adlarını otomatik düzeltme ölçülüp reddedildi (14 iyi, 34 kötü).
  - **Son ölçüm: test seti 1 %90.0 (100 adres, F1 0.976), yeni test seti 2 %94.0 (50 adres, F1 0.989, baseline %44.0), geliştirme 320/323 (%99.1).** Test seti 2 de aynı kişi tarafından, kurallar bilinerek yazıldı ve küçük; gerçek dünya sayısı değil.
  - Demo kod değişince kendini yeniden başlatıyor (`--no-reload` ile kapanır).
  - Bilinen hatalar: `Sinir` (kelime listesinde yok), `Ankara Kızılay Atatürk Blv.`, anahtarsız `Marina Residence`. 144 mahalle yazım farkı açık kaldı.
- [ ] Faz 6 — CLI ve API yüzeyi (2026-11-05, kod bitti; Google Maps denemesi ve onay bekliyor)
  - `cli.py` (argparse, yeni bağımlılık yok): `tradres parse "adres"` (JSON + `adres` anahtarı), `tradres parse-csv girdi.csv --column adres -o cikti.csv`, `python -m tradres`. Excel uyumu: kodlama (BOM → UTF-8 → cp1254) ve ayraç otomatik, çıktı BOM'lu UTF-8. Sonuç sütunları `tradres_` önekli, `tradres_guven`, `tradres_adres`.
  - `Address.format()`: sabit sıra, `kalan` hariç. Tur testi: geliştirme 323/323, karışık alanlı 30.000 adreste 6 sapma (hepsi ilsiz adreste tarif kelimesi yer sanılıyor), test seti 1'de 99/100 (kilitli set açılmadı), test seti 2'de 50/50. Hypothesis 5000 örnekte temiz.
  - Maps biçimi için yeni `google_maps` grubu (24 adres, uydurma numaralar): **önce 0/24, sonra 24/24.** Sondaki ülke adı site/mahalle oluyordu (`data/country_names.json`), Plus Code mahalle oluyordu. Geliştirme 320/347 → 344/347 (%99.1), test setleri değişmedi (%90.0, %94.0).
  - Hız: 10.000 satır CSV 2.6 s (~261 µs/satır, dosya okuma/yazma dahil). Wheel 229 KiB.
  - CI eşiği `--min-tag temiz=0.95 --min-tag google_maps=0.95`: dağınık veri çalışması düzenli adresleri bozarsa build kırılır.
  - Gerçek deneme dosyaları `denemeler/` altında, `.gitignore`'da.
- [ ] Faz 7 — Açık kaynak altyapısı
- [ ] Faz 8 — README ve v0.1.0
- [ ] Faz 9 — Tanıtım

### Kararlar günlüğü
- **Build backend: hatchling.** `uv_build` daha hızlı ama ekosistemde daha yeni; hatchling yaygın, PEP 639 lisans alanını destekliyor ve paket verisini (gazetteer) ekstra ayar olmadan wheel'e alıyor.
- **Sürüm tek kaynakta.** Sürüm `pyproject.toml`'da; `tradres.__version__` bunu `importlib.metadata` ile okuyor, ikinci bir kopya yok.
- **Kapsam eşiği pyproject'te.** `fail_under = 90` hem lokalde hem CI'da aynı kuralı uyguluyor.
- **mypy pre-commit'te `uv run` ile çalışıyor**, izole mirror ortamı yerine. Böylece CI ile aynı bağımlılıkları görüyor.
- **Satır sonları LF** (`.gitattributes`). Windows'ta geliştirip Linux CI'da çalıştırırken diff gürültüsü olmasın diye.
- **Modül adı `normalization.py`** (`normalize.py` değil): paket `normalize` fonksiyonunu dışa açıyor; aynı isimde modül olunca `tradres.normalize` bazen modülü bazen fonksiyonu gösterir.
- **`clean` büyük/küçük harfi korur, `normalize` = `tr_lower(clean(x))`.** Sıra önemli: NFKC bazı sembolleri büyük harfe çevirir (ℌ → H), küçültme en sonda.
- **Rakam/harf ayırma en az 2 harfte** (`23nisan` → `23 nisan`, `no5` → `no 5`) ama `5A`, `B3` korunur (bina no / blok adı). Rakam arası `/` sıkı kalır (`5/3`), diğerleri boşluklu (`Merkez / Bolu`).
- **Kısaltmalar JSON'da**: stdlib ile okunur (YAML bağımlılık ister, TOML 3.10'da stdlib'de yok). Tek kelimelik alias'lar, `alias_key` ile nokta/iki nokta/aksan bağımsız eşleşme. Belirsiz alias'lar (`da`, `bul`) bilerek eklenmedi.
- **ruff `allowed-confusables = ["ı"]`**: ı gerçek bir harf. Diğer benzer görünen karakterler kaynakta `\uXXXX` olarak yazılır.
- **Doctest'ler test paketinin parçası** (`--doctest-modules`): docstring örnekleri yanlış kalamaz.
- **Gazetteer kaynağı Wikidata (CC0).** turkiye-api daha eksiksiz ama veri TÜİK/PTT kaynaklı ve yeniden dağıtım lisansı belirsiz; OSM'de mahalle kapsamı ~%30 ve ODbL share-alike. PTT toplu dosyası kaldırılmış, NVİ kazınamaz. turkiye-api sadece **yerel karşılaştırma** için kullanıldı, pakete girmedi.
- **Wikidata hataları kodda değil, `gazetteer_corrections.json`'da** düzeltiliyor; her girdi QID + gerekçe içeriyor, Wikidata düzelince silinir. Eski/halk adları (`Kazan`, `Eyüp`, `Urfa`, `Afyon`) `diger_adlar` olarak tutuluyor, resmi ad olarak gösterilmiyor.
- **Merkez ilçe kuralı:** büyükşehir olmayan 51 ilde ilin adını taşıyan ilçe `Merkez` olur; 30 büyükşehirde bu tür kayıtlar eskimiş sayılıp atılır (sabit liste: 6360 + Ordu 6447).
- **Mahalle ve köy ayrılmıyor** (`Mahalle` sınıfı ikisini de tutar): Wikidata sınıfı güvenilir değil.
- **İndeks: ASCII anahtarlı `dict`**, trie değil. Tam eşleşme O(1); trie sadece önek/bulanık aday aramasında gerekir, şimdilik yok — Faz 5'te ölçülür.
- **Değerlendirme seti YAML** (PyYAML sadece dev): katkıcı için okunabilirlik ve yorum satırı en önemli kriter.
- **`bina_adi` yeni alan** (`Gül Apartmanı` → `Gül`): `kalan`'da kalsa ölçümü yanıltırdı.
- **Karşılaştırma büyük/küçük harfe duyarsız, Türkçe harfe duyarlı.** `Cankaya` yanlış sayılır; doğru yazımı geri vermek ürünün vaadi. Adlar tür eksiz, numaralar metin.
- **Set gazetteer'dan örneklenmedi.** Kök nüfus ağırlıklı rastgele örneklem (sabit tohum), yoksa eksik %11 ölçümde görünmezdi. Sokak, bina ve numaralar uydurma; Aykan'ın adresi örneklem dışında.
- **`kalan` şimdilik puanlanmıyor;** sadece belge. Hatalı değer hem FP hem FN sayılır. Parser hata fırlatırsa boş sonuç + `crashes` sayacı.
- **Parser token tabanlı, kural tabanlı.** Aşamalar saf fonksiyon ve kullandığı token'ları bildiriyor; hiçbir aşamanın kullanmadığı token `kalan`'a düşüyor.
- **Sıra: sayılar → il/ilçe → adlar.** Türkçede ad önce, anahtar sonra gelir (`Gazi Mustafa Kemal Bulvarı`); bu yüzden boş kelimeler biriktirilip sonraki anahtara veriliyor. Anahtardan hemen önceki kelime il/ilçe sayılmıyor (`Van Cad.`, `Fatih Mah.`).
- **Alan ezilmez:** bir alan ilk değerini tutar, sonraki değer `kalan`'a gider. Hypothesis (5000 örnek) `D: 34000 12/3`'te daire ezilmesini yakaladı.
- **Çıplak `D` + 3 hane daire sayılmaz** (`D 100` karayolu); `D:100` ve `Daire 100` sayılır.
- **Web demosu Faz 4 sonunda, stdlib ile** (`http.server`): parser olmadan gösterecek şey yoktu; bağımlılık eklememek için FastAPI kullanılmadı. Hugging Face demosu v0.2 planında kalıyor.
- **Tarif sözcüğü kuralı sadece bina adında:** `Cami Yanı Sokak`, `Kale Arkası Cad.` gerçek sokak adları, bu yüzden cadde/sokakta uygulanmıyor. `... Lojmanları` şimdilik `kalan`'a gidiyor.
- **Hedef daraltıldı (2026-11-05, Aykan):** TrAdres bir form aracı değil, veri temizleme aracı: dağınık adres içeren CSV ve eski kayıtları temizleyen, CLI odaklı kütüphane. Yeni formlarda ayrı kutular daha iyi. Talep ve rakip araştırması şimdilik yapılmadı; README ve tanıtımda büyük talep iddiası yazılmayacak.
- **Gerçek adres denemesi Faz 6 sonunda:** Aykan internetten bulduğu adresleri `tradres parse-csv` ile toplu dener. Hatalar kalıp olarak geliştirme setine girer; numaralar ve binalar uydurulur, adresler olduğu gibi depoya girmez.
- **CLI argparse ile (Aykan seçti):** typer/click eklemek `pip install tradres[cli]` adımı getirirdi; ilerleme çubuğu kendi kodumuz, ~30 satır.
- **CSV sonuç sütunları `tradres_` önekli (Aykan seçti):** girdideki `il` sütunuyla çakışmaz. Kendi çıktısını ikinci kez işlemek hata verir.
- **Ayraç veri sezilerek değil, `--column` adıyla bulunur:** adreslerde virgül bol olduğu için `csv.Sniffer` güvenilmez; doğru ayraç kullanıcının verdiği sütunu bulan ayraçtır.
- **Fazla hücre son sütuna birleşir:** tırnaksız virgüllü adres satırı metin kaybetmez, özette uyarı çıkar.
- **Formül koruması:** `=`, `+`, `-`, `@` ile başlayan yeni hücrelerin başına `'` eklenir (CSV injection: Excel hücreyi formül diye çalıştırabilir). Girdi sütunlarına dokunulmaz.
- **Ülke adı sadece adresin son kelimesiyse atılır:** `Türkiye Sk.` sokak olarak kalır.
- **Deneme sırası:** önce düzenli adresler (Google Maps) oturtulacak, karmaşık veri ondan sonra ele alınacak (Aykan, 2026-11-05). v0.1 hedefi dağınık CSV temizliği olduğu için karmaşık veri denemesi unutulmamalı.
- **Faz 6'dan önce yer verisi güçlendirilecek** (Aykan kabul etti); kaynak seçimi Aykan'da.
- **Fuzzy: rapidfuzz + OSA.** Takas (`Malatay`) 1 düzeltme sayılır. Eşitlikte tahmin edilmez. Kısa kelime düzeltilmez (`Van`/`Yan`). Mahalle için alt sınır daha yüksek: eksik bir `Çınar` `Pınar` olmamalı.
- **Birebir ad, fuzzy'den önce gelir:** Türkiye'nin herhangi bir yerinde birebir geçen mahalle gerçek ad sayılır (`Ulucami` → `Uluçam` hatası böyle çözüldü).
- **Harf geri getirme sadece tamamen ASCII kelimede:** kelime listesi gazetteer'dan, en sık yazım seçilir. Kullanıcının Türkçe harflerine dokunulmaz.
- **Güven skoru kural tabanlı:** alanın bulunma biçimi (`Origin`) puanı verir, olasılık değildir.
- **`pip` dev grubunda:** VS Code Python eklentisi `pip list` çalıştırıyor; uv ortamında pip yok.
- **Etiket dili önceliği tr → mul → en → …**: Wikidata ortak adları `mul` diline taşıyor; sadece `tr` sorgusu 12 ilçeyi kaçırıyordu.

---

**Kaldığımız yer:** İlerleme bölümündeki ilk tamamlanmamış faz.
