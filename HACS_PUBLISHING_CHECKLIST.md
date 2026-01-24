# HACS Publishing Checklist

This document tracks compliance with HACS publishing requirements for the Omada Open API integration.

**Documentation Reference**: https://github.com/hacs/documentation/tree/main/source/docs/publish

---

## General Requirements (All Repositories)

### ✅ Repository Settings
- [x] **Public repository** on GitHub
- [x] **Description** set: "Home Assistant integration for TP-Link Omada SDN using the Open API"
- [x] **Topics** added: home-assistant, home-assistant-integration, hacs, omada, tp-link, sdn, network-monitoring, custom-component
- [x] **README.md** present with usage information
- [x] **hacs.json** file in repository root

### ✅ Version Management
- [ ] **GitHub Releases** (recommended but optional)
  - Status: Using commit-based versioning currently
  - Recommendation: Create first release tag matching manifest.json version (0.1.0)

### ✅ HACS Manifest (hacs.json)
- [x] `name`: "TP-Link Omada SDN"
- [x] `homeassistant`: "2024.1.0" (minimum HA version)
- [x] `render_readme`: true (render README in HACS)

---

## Integration-Specific Requirements

### ✅ Repository Structure
- [x] **Correct directory structure**:
  ```
  custom_components/
    omada_open_api/
      __init__.py
      sensor.py
      binary_sensor.py
      device_tracker.py
      config_flow.py
      coordinator.py
      api.py
      const.py
      manifest.json
      strings.json
      translations/
        en.json
      icon.png
      icon@2x.png
      logo.png
      logo@2x.png
  hacs.json
  README.md
  ```
- [x] Only one integration in repository
- [x] All integration files in `custom_components/omada_open_api/`

### ✅ manifest.json Requirements
- [x] `domain`: "omada_open_api"
- [x] `name`: "TP-Link Omada SDN"
- [x] `documentation`: "https://github.com/bullitt186/ha-omada-open-api"
- [x] `issue_tracker`: "https://github.com/bullitt186/ha-omada-open-api/issues"
- [x] `codeowners`: ["@bullitt186"]
- [x] `version`: "0.1.0"

### ⚠️ Home Assistant Brands (CRITICAL)
- [ ] **Brand assets submitted** to [home-assistant/brands](https://github.com/home-assistant/brands)
  - Status: Local assets exist (icon.png, logo.png, etc.)
  - **ACTION REQUIRED**: Submit PR to home-assistant/brands repository
  - Process:
    1. Fork home-assistant/brands
    2. Add assets to `custom_integrations/omada_open_api/`
    3. Submit PR with assets
    4. Wait for approval and merge

---

## Current Status Summary

### ✅ Compliant (6/8 requirements)
1. ✅ Repository is public on GitHub
2. ✅ Repository has description
3. ✅ README.md exists with comprehensive documentation
4. ✅ Correct repository structure
5. ✅ manifest.json has all required fields
6. ✅ hacs.json created

### ⚠️ Needs Action (2/8 requirements)
1. ⚠️ **GitHub Topics** - Need to add topics for searchability
2. ⚠️ **Home Assistant Brands** - Must submit brand assets PR (CRITICAL for HACS)

### 📝 Recommended (Optional)
1. 📝 **GitHub Releases** - Create first release tag (v0.1.0)
2. 📝 **Enhanced README** - Add HACS installation badge/instructions

---

## Action Items

### Priority 1: Critical (Required for HACS)

#### 1. Submit Brand Assets to home-assistant/brands
**Status**: ❌ Not Started
**Requirement**: CRITICAL - HACS will not accept integration without this

**Steps**:
1. Fork https://github.com/home-assistant/brands
2. Create directory: `custom_integrations/omada_open_api/`
3. Copy brand assets:
   - `icon.png` (256x256)
   - `icon@2x.png` (512x512)
   - `logo.png` (256x128)
   - `logo@2x.png` (512x256)
4. Create `manifest.json` in brand directory:
   ```json
   {
     "domain": "omada_open_api",
     "name": "TP-Link Omada SDN",
     "integrations": ["omada_open_api"]
   }
   ```
5. Submit PR to home-assistant/brands
6. Wait for review and merge

**Estimated Time**: 30 minutes + review time
**Blocker**: Yes - Cannot publish to HACS without this

#### 2. Add GitHub Topics
**Status**: ❌ Not Started

**Recommended Topics**:
- `home-assistant`
- `home-assistant-integration`
- `hacs`
- `omada`
- `tp-link`
- `sdn`
- `network-monitoring`
- `custom-component`

**Steps**:
1. Go to GitHub repository settings
2. Add topics in "About" section
3. Save changes

**Estimated Time**: 2 minutes

### Priority 2: Recommended (Best Practice)

#### 3. Create First GitHub Release
**Status**: ❌ Not Started

**Steps**:
1. Ensure all code is committed and pushed
2. Create and push tag: `git tag -a v0.1.0 -m "Initial HACS release"`
3. Push tag: `git push origin v0.1.0`
4. Create release on GitHub from tag
5. Add release notes describing features

**Benefits**:
- Users can select specific versions in HACS
- Better version tracking
- Professional appearance

**Estimated Time**: 15 minutes

#### 4. Enhance README for HACS Users
**Status**: ❌ Not Started

**Additions**:
1. Add HACS installation badge
2. Add HACS installation instructions
3. Add screenshots of integration in HA UI
4. Add configuration examples

**Estimated Time**: 30 minutes

---

## Publishing Process

### Step 1: Complete All Critical Actions
1. Submit brand assets PR to home-assistant/brands
2. Add GitHub topics
3. Wait for brand assets PR to be merged

### Step 2: Test Integration Locally
1. Install via HACS custom repository
2. Verify all features work
3. Check UI displays correctly

### Step 3: Submit to HACS Default Repository (Optional)
If you want your integration discoverable in HACS by default:
1. Go to https://github.com/hacs/default
2. Submit PR adding your repository to `integration` file
3. Provide description and screenshots
4. Wait for review and approval

**Note**: This step is optional - users can always add your integration as a custom repository.

---

## Resources

- **HACS Publishing Docs**: https://github.com/hacs/documentation/tree/main/source/docs/publish
- **Home Assistant Brands**: https://github.com/home-assistant/brands
- **HACS Default Submissions**: https://github.com/hacs/default
- **Integration Quality Scale**: https://developers.home-assistant.io/docs/integration_quality_scale_index
- **My Home Assistant Links**: https://my.home-assistant.io/create-link/?redirect=hacs_repository

---

## Validation Commands

```bash
# Validate hacs.json
cat hacs.json | jq .

# Validate manifest.json
cat custom_components/omada_open_api/manifest.json | jq .

# Check repository structure
tree -L 3 custom_components/

# Verify brand assets exist
ls -lh custom_components/omada_open_api/*.png

# Check version consistency
grep version custom_components/omada_open_api/manifest.json
git tag --list
```

---

## Timeline Estimate

### Minimum Path to HACS Publishing
1. **Brand Assets PR**: 30 min + 1-7 days review time
2. **GitHub Topics**: 2 minutes
3. **Testing**: 30 minutes
4. **Total**: ~1 hour work + waiting for brands PR approval

### Recommended Path (with Release)
1. All of the above
2. **First Release**: 15 minutes
3. **README Enhancement**: 30 minutes
4. **Total**: ~2 hours work + waiting for brands PR approval

---

## Post-Publishing

After HACS acceptance:
1. Update README with HACS badge
2. Add "Available in HACS" note
3. Create announcement/blog post
4. Update Home Assistant community forum thread
5. Monitor issues and provide support

---

**Last Updated**: 2026-01-24
**Current Version**: 0.1.0
**HACS Ready**: ❌ (waiting on brand assets PR)
