export interface PlantMetric {
  plant: string;
  name: string;
  facilityType: string;
  totalBins: number;
  occupiedBins: number;
  inventoryQty: number;
  utilizationPct: number;
  status: string;
}

export interface DashboardSummary {
  total_inventory: number;
  occupied_bins: number;
  total_bins: number;
  active_materials: number;
  overall_utilization: number;
  putaway_throughput: number;
  putaway_on_time_pct: number;
}

export interface WarehouseStatsResponse {
  plant_count: number;
  plants: PlantMetric[];
  summary: DashboardSummary;
}
