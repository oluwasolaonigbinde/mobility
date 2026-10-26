"use client";
import type { ApplicationCar } from "./application-journey";

export function CarChooser({ cars }: { cars: ApplicationCar[] }) {
  if (!cars.length) return null;
  return (
    <fieldset className="border-edge rounded-lg border p-4">
      <legend className="px-1 text-sm">Which car are you updating?</legend>
      <div className="grid gap-3 text-sm">
        {cars.map((car) => (
          <label key={car.vehicle_id} className="flex items-center gap-2">
            <input
              type="radio"
              name="vehicle_id"
              value={car.vehicle_id}
              defaultChecked={cars.length === 1}
              required
            />
            {car.plate_number}
          </label>
        ))}
        <label className="flex items-center gap-2">
          <input type="radio" name="vehicle_id" value="" required />A different car
        </label>
      </div>
    </fieldset>
  );
}
