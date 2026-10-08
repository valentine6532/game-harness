#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "NyabloClothTools.generated.h"

class USkeletalMesh;

/**
 * Editor-only helpers called from Scripts/ue_build_plaza.py (Python has no API to create clothing data).
 */
UCLASS()
class NYABLO_API UNyabloClothTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * Builds a Chaos cloth asset from mesh section SimSection (LOD 0; a welded low-res proxy, removed from the render mesh)
	 * and binds it to RenderSection (the visible cloth, skinned to the sim mesh). Paints Max Distance:
	 * per connected cloth island, vertices within PinBand (cm) of the island's end along PinDirection (the top for a cape,
	 * the root for a tail) stay skinned (0),
	 * below that the allowed distance grows by Slope cm per cm, capped at MaxDistanceCap.
	 * AnimDrive > 0 springs particles back to the animated shape (keeps a tube like a tail from collapsing).
	 * ConfigOverrides sets Chaos cloth config properties by name: float properties, weighted values (Low = High)
	 * and vectors (X = Y = Z), e.g. {"GravityScale": 0.6, "Drag": 0.2, "Lift": 0.2, "LinearVelocityScale": 1.0}.
	 * Body collision comes from the mesh's physics asset. Returns the number of simulated vertices (0 = failed).
	 */
	UFUNCTION(BlueprintCallable, Category = "Nyablo|Cloth")
	static int32 SetupSectionCloth(USkeletalMesh* Mesh, int32 RenderSection, int32 SimSection, FVector PinDirection, float PinBand,
		float Slope, float MaxDistanceCap, float AnimDrive,
		const TMap<FString, float>& ConfigOverrides);
};
