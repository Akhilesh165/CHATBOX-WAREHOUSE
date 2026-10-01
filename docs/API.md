# Warehouse Inventory AI API Documentation

## Overview
The Warehouse Inventory AI Assistant API provides a secure, natural-language interface for querying warehouse inventory quantities, bin locations, storage locations, plant distributions, and material master attributes.

Base URL: `http://localhost:8000`

---

## Endpoints

### 1. Health Check
`GET /api/health` (or `GET /health`)

Returns database and service connectivity status without exposing credentials.

**Response:**
```json
{
  "status": "ok",
  "app": "Warehouse Inventory AI API",
  "version": "1.0.0",
  "database": "ok"
}
```

---

### 2. Chat Query
`POST /api/chat`

Translates a natural language warehouse question into validated SQL Server T-SQL, executes it with read-only permissions, and returns a grounded answer with tabular data, chart metadata, and execution meta.

**Request Body:**
```json
{
  "message": "Show top 10 materials by quantity",
  "conversation_id": "optional-id"
}
```

**Response Body:**
```json
{
  "answer": "Here are the top 10 materials by unrestricted inventory quantity. Material 1000234 leads with 15,200 EA.",
  "data": [
    {
      "Material": "1000234",
      "MaterialDescription": "Corrugated Shipping Box XL",
      "TotalQuantity": 15200.0
    }
  ],
  "chart": {
    "type": "bar",
    "title": "Top 10 Materials by Inventory",
    "xAxis": "Material",
    "yAxis": "TotalQuantity",
    "data": [
      {
        "Material": "1000234",
        "TotalQuantity": 15200.0
      }
    ]
  },
  "meta": {
    "requestId": "req-9b87f2e1a4",
    "rowCount": 10,
    "executionMs": 123
  }
}
```

*Note: The `sql` query string is included in the response when `is_admin=true` or when server `DEBUG=True`.*

---

### 3. Schema Metadata (Admin Only)
`GET /api/schema`

Returns approved table/view names and column definitions for debugging. Does not return secrets or connection strings.

**Response:**
```json
{
  "tables": {
    "dbo.ZWMS_INVENTORY": {
      "source": "Bin Invrntory.xlsx (Sheet1)",
      "description": "Authoritative inventory quantities, bins, batches, and plants",
      "columns": ["Id", "FileName", "Material", "Plant", "StorageLocation", "Batch", "MaterialDescription", "UnrestrictedQty", "UnrestrictedQty2", "BaseUnitOfMeasure", "Mrp", "FullyVestedOn", "ChangedAt", "BinNo", "INSERT_BY", "INSERT_TIMESTAMP", "UPDATE_BY", "UPDATE_TIMESTAMP"]
    },
    "dbo.ZWMS_BIN_MASTER": {
      "source": "WMS Bins Data.xlsx (Bin Master)",
      "description": "Bin dimensions, volume, pallet types, and storage locations",
      "columns": ["Id", "Plant", "BinLocation", "MainCriterion", "StorageLocation", "PalletType", "Box", "Owner", "Volume", "VolumeUnit", "Length", "Width", "Height", "CreatedDate", "CreatedBy"]
    },
    "dbo.ZWMS_MATERIAL_MASTER": {
      "source": "WMS Bins Data.xlsx (Material Master)",
      "description": "Material physical specs, divisions, weights, groups, and packaging",
      "columns": ["Id", "MaterialCode", "MaterialDescription", "Volume", "VUom", "GrossWeight", "Division", "DivisionDescription", "Kslot", "BinUom", "InsertBY", "CreatedDateTime", "NetWeight", "EanNo", "Hierarchy", "MaterialGroup", "CaseLot", "Length", "Width", "Height", "CartoonGrossWeight", "CartoonVolume", "UpdatedDateTime"]
    },
    "dbo.vw_WMS_InventoryEnriched": {
      "source": "Semantic View",
      "description": "Unified inventory view joined with Bin and Material master attributes"
    }
  }
}
```

---

### 4. Submit Feedback
`POST /api/feedback`

Records user satisfaction rating (thumbs up / down) and comments.

**Request Body:**
```json
{
  "conversation_id": "session-123",
  "rating": "up",
  "comment": "Accurate figures and chart."
}
```

**Response Body:**
```json
{
  "status": "recorded",
  "message": "Thank you for your feedback!"
}
```
