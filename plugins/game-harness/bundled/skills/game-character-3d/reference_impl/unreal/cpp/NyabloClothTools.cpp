#include "NyabloClothTools.h"

#include "Engine/SkeletalMesh.h"
#include "PhysicsEngine/PhysicsAsset.h"

#if WITH_EDITOR
#include "ClothingAsset.h"
#include "ClothingAssetFactoryInterface.h"
#include "ClothingSystemEditorInterfaceModule.h"
#include "Modules/ModuleManager.h"
#include "PointWeightMap.h"
#endif

DEFINE_LOG_CATEGORY_STATIC(LogNyabloCloth, Log, All);

int32 UNyabloClothTools::SetupSectionCloth(USkeletalMesh* Mesh, int32 RenderSection, int32 SimSection, FVector PinDirection, float PinBand,
	float Slope, float MaxDistanceCap, float AnimDrive, const TMap<FString, float>& ConfigOverrides)
{
#if WITH_EDITOR
	if (!Mesh)
	{
		return 0;
	}
	FClothingSystemEditorInterfaceModule& ClothModule =
		FModuleManager::LoadModuleChecked<FClothingSystemEditorInterfaceModule>(TEXT("ClothingSystemEditorInterface"));
	UClothingAssetFactoryBase* Factory = ClothModule.GetClothingAssetFactory();
	if (!Factory)
	{
		UE_LOG(LogNyabloCloth, Error, TEXT("NYABLO_CLOTH no clothing asset factory"));
		return 0;
	}

	FSkeletalMeshClothBuildParams Params;
	Params.AssetName = FString::Printf(TEXT("%s_Cloth%d"), *Mesh->GetName(), RenderSection);
	Params.LodIndex = 0;
	Params.SourceSection = SimSection;
	Params.bRemoveFromMesh = SimSection != RenderSection;
	Params.PhysicsAsset = Mesh->GetPhysicsAsset();
	UClothingAssetCommon* Cloth = Cast<UClothingAssetCommon>(Factory->CreateFromSkeletalMesh(Mesh, Params));
	if (!Cloth || Cloth->LodData.Num() == 0)
	{
		UE_LOG(LogNyabloCloth, Error, TEXT("NYABLO_CLOTH CreateFromSkeletalMesh failed for section %d"), SimSection);
		return 0;
	}
	Mesh->AddClothingAsset(Cloth);

	FClothLODDataCommon& Lod = Cloth->LodData[0];
	const TArray<FVector3f>& Verts = Lod.PhysicalMeshData.Vertices;
	const TArray<uint32>& Indices = Lod.PhysicalMeshData.Indices;
	const int32 Num = Verts.Num();

	// connected islands (union-find over triangles) -> top height of each island
	TArray<int32> Parent;
	Parent.SetNumUninitialized(Num);
	for (int32 i = 0; i < Num; ++i)
	{
		Parent[i] = i;
	}
	TFunction<int32(int32)> Find = [&Parent, &Find](int32 X) -> int32
	{
		while (Parent[X] != X)
		{
			Parent[X] = Parent[Parent[X]];
			X = Parent[X];
		}
		return X;
	};
	for (int32 t = 0; t + 2 < Indices.Num(); t += 3)
	{
		const int32 A = Find(Indices[t]);
		for (int32 k = 1; k < 3; ++k)
		{
			const int32 B = Find(Indices[t + k]);
			if (A != B)
			{
				Parent[B] = A;
			}
		}
	}
	const FVector3f Dir = FVector3f(PinDirection.GetSafeNormal());
	TMap<int32, float> IslandTop;
	for (int32 i = 0; i < Num; ++i)
	{
		float& Top = IslandTop.FindOrAdd(Find(i), -FLT_MAX);
		Top = FMath::Max(Top, FVector3f::DotProduct(Verts[i], Dir));
	}

	FPointWeightMap MaxDistance;
	MaxDistance.Initialize(Num);
	MaxDistance.CurrentTarget = (uint8)EWeightMapTargetCommon::MaxDistance;
	MaxDistance.bEnabled = true;
	MaxDistance.Name = TEXT("MaxDistance");
	int32 Free = 0;
	for (int32 i = 0; i < Num; ++i)
	{
		const float Below = IslandTop[Find(i)] - FVector3f::DotProduct(Verts[i], Dir);
		const float Value = FMath::Clamp((Below - PinBand) * Slope, 0.f, MaxDistanceCap);
		MaxDistance.Values[i] = Value;
		Free += Value > 0.f ? 1 : 0;
	}
	Lod.PointWeightMaps.Add(MaxDistance);
	Cloth->ApplyParameterMasks();

	if (AnimDrive > 0.f)
	{
		// UChaosClothConfig lives in the ChaosCloth plugin: set its properties by reflection (no module dependency)
		for (const TPair<FName, TObjectPtr<UClothConfigBase>>& Pair : Cloth->ClothConfigs)
		{
			UObject* Config = Pair.Value;
			FStructProperty* Prop = Config ? FindFProperty<FStructProperty>(Config->GetClass(), TEXT("AnimDriveStiffness")) : nullptr;
			if (Prop)
			{
				float* LowHigh = Prop->ContainerPtrToValuePtr<float>(Config);   // FChaosClothWeightedValue { Low, High }
				LowHigh[0] = AnimDrive;
				LowHigh[1] = AnimDrive;
				UE_LOG(LogNyabloCloth, Log, TEXT("NYABLO_CLOTH anim drive %.2f on %s"), AnimDrive, *Config->GetClass()->GetName());
			}
		}
		FPointWeightMap Drive;
		Drive.Initialize(Num);
		Drive.CurrentTarget = (uint8)EWeightMapTargetCommon::AnimDriveStiffness;
		Drive.bEnabled = true;
		Drive.Name = TEXT("AnimDrive");
		for (int32 i = 0; i < Num; ++i)
		{
			Drive.Values[i] = 1.f;
		}
		Lod.PointWeightMaps.Add(Drive);
		Cloth->ApplyParameterMasks();
	}

	for (const TPair<FName, TObjectPtr<UClothConfigBase>>& Pair : Cloth->ClothConfigs)
	{
		UObject* Config = Pair.Value;
		if (!Config || !Config->GetClass()->GetName().Contains(TEXT("ChaosClothConfig")))
		{
			continue;
		}
		for (const TPair<FString, float>& Override : ConfigOverrides)
		{
			FProperty* Prop = FindFProperty<FProperty>(Config->GetClass(), FName(*Override.Key));
			void* Ptr = Prop ? Prop->ContainerPtrToValuePtr<void>(Config) : nullptr;
			bool bSet = false;
			if (FFloatProperty* F = CastField<FFloatProperty>(Prop))
			{
				F->SetPropertyValue(Ptr, Override.Value);
				bSet = true;
			}
			else if (FStructProperty* St = CastField<FStructProperty>(Prop))
			{
				if (St->Struct->GetFName() == NAME_Vector)
				{
					*static_cast<FVector*>(Ptr) = FVector(Override.Value);
					bSet = true;
				}
				else if (St->Struct->GetName().Contains(TEXT("WeightedValue")))
				{
					static_cast<float*>(Ptr)[0] = Override.Value;   // FChaosClothWeightedValue { Low, High }
					static_cast<float*>(Ptr)[1] = Override.Value;
					bSet = true;
				}
			}
			UE_LOG(LogNyabloCloth, Log, TEXT("NYABLO_CLOTH config %s = %.3f %s"), *Override.Key, Override.Value, bSet ? TEXT("") : TEXT("(NOT FOUND)"));
		}
	}

	// removing the sim section shifts the sections after it
	const int32 BindSection = (Params.bRemoveFromMesh && SimSection < RenderSection) ? RenderSection - 1 : RenderSection;
	if (!Cloth->BindToSkeletalMesh(Mesh, 0, BindSection, 0))
	{
		UE_LOG(LogNyabloCloth, Error, TEXT("NYABLO_CLOTH BindToSkeletalMesh failed"));
		return 0;
	}
	Mesh->PostEditChange();
	Mesh->MarkPackageDirty();
	UE_LOG(LogNyabloCloth, Log, TEXT("NYABLO_CLOTH %s render=%d sim=%d simverts=%d free=%d islands=%d"),
		*Mesh->GetName(), BindSection, SimSection, Num, Free, IslandTop.Num());
	return Free;
#else
	return 0;
#endif
}
